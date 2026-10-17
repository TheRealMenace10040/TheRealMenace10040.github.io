"""
MicroQC Insight: clean a Power BI LIMS model into a Tableau-ready workbook.

Reads MicroQC_Insight.pbix, pulls the source tables out of the compressed
data model, cleans them, and writes:
  MicroQC_Insight_Clean.xlsx  one row-per-result fact table, supporting tables,
                              a data dictionary and a step-by-step cleaning log
  data.js                     the compact dataset the dashboard page loads

Usage:  python clean_microqc.py MicroQC_Insight.pbix
Needs:  pip install pbixray pandas openpyxl

All data is simulated LabWare-style LIMS data. No real site data is used.
"""
import json
import os
import sys

import numpy as np
import pandas as pd
from openpyxl.styles import Font, PatternFill
from pbixray import PBIXRay

SOURCE_TABLES = ['SAMPLE', 'TEST', 'RESULT', 'flagged_results', 'LOT', 'INVESTIGATION',
                 'PRODUCT_SPEC', 'INSTRUMENTS', 'LIMS_USERS', 'AUDIT_TRAIL']

ANALYSIS = {'SETTLE_PLATE_TSA': 'Settle Plate (TSA)', 'VIABLE_AIR_USP': 'Active Air Sample',
            'BIOBURDEN_USP61': 'Bioburden', 'LAL_KINETIC': 'Endotoxin (Kinetic LAL)',
            'WATER_BIOBURDEN': 'Water Bioburden'}
SAMPLE_TYPE = {'EM_SURFACE': 'EM - Surface', 'EM_AIR': 'EM - Air',
               'BIOBURDEN': 'Product - Bioburden', 'ENDOTOXIN': 'Product - Endotoxin'}
GRADE = {'A': 'Grade A (ISO 5)', 'B': 'Grade B (ISO 5/7)', 'C': 'Grade C (ISO 7)', 'D': 'Grade D (ISO 8)'}

log = []


def note(category, table, action, rows):
    log.append(dict(Step=len(log) + 1, Category=category, Table=table, Action=action, Rows_Affected=rows))


def to_minute(df, cols):
    """Power BI stores datetimes as floats, so values come back as 09:59:59.999999786."""
    for c in cols:
        df[c] = pd.to_datetime(df[c], errors='coerce').dt.round('min')


def load(pbix_path):
    model = PBIXRay(pbix_path)
    # The other 25 tables are Power BI auto date tables and the _KPIs measure table.
    # Blank text comes back as '' rather than null, so normalise it.
    return {t: model.get_table(t).replace('', np.nan) for t in SOURCE_TABLES}


def clean(t):
    S, T, R, F = t['SAMPLE'], t['TEST'], t['RESULT'], t['flagged_results']
    LOT, INV, PS, INS, U, A = (t[k] for k in ['LOT', 'INVESTIGATION', 'PRODUCT_SPEC', 'INSTRUMENTS', 'LIMS_USERS', 'AUDIT_TRAIL'])
    note('Scope', 'Model', 'Removed 23 auto-generated Power BI LocalDateTable/DateTableTemplate tables and the _KPIs measure table (not source data)', 25)

    n = len(R)
    R = R.drop_duplicates()
    F = F.drop_duplicates()
    assert R.RESULT_NUMBER.is_unique
    note('Duplicates', 'RESULT', 'Removed exact duplicate rows (RESULT_NUMBER 901518, 903080, 904214 each loaded twice)', n - len(R))

    to_minute(S, ['LOGIN_DATE', 'CHANGED_ON', 'DUE_DATE', 'DATE_RECEIVED', 'DATE_COMPLETED', 'DATE_REVIEWED'])
    to_minute(R, ['ENTERED_ON', 'REVIEWED_ON'])
    to_minute(T, ['DATE_STARTED'])
    to_minute(LOT, ['MFG_DATE', 'RELEASED_ON'])
    to_minute(INV, ['OPENED', 'CLOSED'])
    to_minute(A, ['CHANGED_ON'])
    INS['CALIB_DUE'] = pd.to_datetime(INS.CALIB_DUE)
    note('Formatting', 'All', 'Rounded timestamps to nearest minute (removed floating-point noise like 09:59:59.999999786 and 08:00:00.000000213)', len(S) * 6)

    uname = dict(zip(U.USER_NAME, U.FULL_NAME))

    # ---- fact table: one row per result ----
    inv = INV.copy()
    inv['Investigation_Days'] = ((inv.CLOSED - inv.OPENED).dt.total_seconds() / 86400).round(1)
    aud = A.groupby('RECORD_KEY').agg(Audit_Corrections=('FIELD', 'size'), Original_Entry=('OLD_VALUE', 'first')).reset_index()
    oot = F[['Sample.Sample_Number', 'Flag_OOT']].drop_duplicates().rename(columns={'Sample.Sample_Number': 'SAMPLE_NUMBER'})
    f = (S.merge(T[['TEST_NUMBER', 'SAMPLE_NUMBER', 'INSTRUMENT', 'DATE_STARTED']], on='SAMPLE_NUMBER', how='left')
         .merge(R, on='TEST_NUMBER', how='left', validate='1:1')
         .merge(oot, on='SAMPLE_NUMBER', how='left', validate='1:1')
         .merge(inv[['RESULT_NUMBER', 'INV_ID', 'CAPA_ID', 'Investigation_Days']], on='RESULT_NUMBER', how='left')
         .merge(aud, left_on='RESULT_NUMBER', right_on='RECORD_KEY', how='left'))
    assert len(f) == len(S)

    e, act, al = f.NUMERIC_ENTRY, f.MAX_LIMIT, f.ALERT_LIMIT
    tat = (f.DATE_COMPLETED - f.LOGIN_DATE).dt.total_seconds() / 86400
    res = pd.DataFrame({
        'Result_ID': f.RESULT_NUMBER, 'Sample_ID': f.SAMPLE_NUMBER, 'Test_ID': f.TEST_NUMBER,
        'Login_Date': f.LOGIN_DATE, 'Login_Month': f.LOGIN_DATE.dt.to_period('M').dt.to_timestamp(),
        'Due_Date': f.DUE_DATE, 'Date_Completed': f.DATE_COMPLETED, 'Date_Reviewed': f.DATE_REVIEWED,
        'Sample_Category': np.where(f.SAMPLE_TYPE.str.startswith('EM'), 'Environmental Monitoring', 'Product Release'),
        'Sample_Type': f.SAMPLE_TYPE.map(SAMPLE_TYPE), 'Analysis': f.NAME.map(ANALYSIS), 'Analysis_Code': f.NAME,
        'Location': f.LOCATION, 'Cleanroom_Grade': f.PRODUCT_GRADE.map(GRADE).fillna('N/A (QC Lab)'),
        'Sampling_Point': f.SAMPLING_POINT.str.replace('_', ' ').str.title().fillna('N/A (Product Sample)'),
        'Product': f.PRODUCT.fillna('N/A (EM Sample)'), 'Lot': f.LOT.fillna('N/A (EM Sample)'),
        'Instrument': f.INSTRUMENT.fillna('Not Recorded'),
        'Result': e, 'Units': f.UNITS, 'Alert_Limit': al, 'Action_Limit': act,
        'Pct_of_Action_Limit': (e / act).round(3),
        # Source rules, confirmed against the Power BI flags: OOS = result >= action, Alert = alert <= result < action
        'Result_Status': np.select([e >= act, e >= al], ['OOS / Action', 'Alert'], 'Within Limits'),
        'Is_OOS': e >= act, 'Is_Alert': (e >= al) & (e < act), 'Is_OOT': f.Flag_OOT.astype(bool),
        'Is_Zero_Count': e.eq(0),
        'TAT_Days': tat.round(2), 'TAT_Breach_4d_SLA': tat > 4, 'Past_Due_Date': f.DATE_COMPLETED > f.DUE_DATE,
        'Analyst': f.ENTERED_BY.map(uname), 'Result_Reviewer': f.REVIEWED_BY.map(uname).fillna('MISSING'),
        'Sample_Reviewer': f.REVIEWER.map(uname),
        'Missing_Reviewer': f.REVIEWED_BY.isna(), 'Self_Reviewed': f.ENTERED_BY.eq(f.REVIEWED_BY).fillna(False).astype(bool),
        'Audit_Corrections': f.Audit_Corrections.fillna(0).astype(int), 'Original_Entry_Before_Correction': f.Original_Entry,
        'Investigation_ID': f.INV_ID.astype('Int64'), 'CAPA_ID': f.CAPA_ID, 'Investigation_Days': f.Investigation_Days,
    })

    # The rebuilt flags must match what the Power BI model calculated
    fo = F.set_index('Sample.Sample_Number').reindex(res.Sample_ID)
    assert (res.Is_OOS.values == fo.Flag_OOS.values).all()
    assert (res.Is_Alert.values == fo.Flag_Alert.values).all()
    assert (res.TAT_Breach_4d_SLA.values == fo.Flag_TAT_Breach.values).all()

    note('Modeling', 'Results', f'Joined SAMPLE + TEST + RESULT + OOT flag + investigations + audit trail into one row-per-result fact table (validated 1:1, {len(res):,} rows; OOS/Alert/TAT flags match original Power BI flags 100%)', len(res))
    note('Dropped columns', 'SAMPLE/TEST/RESULT', 'Removed single-value columns (STATUS=A, OLD_STATUS=U, STANDARD=F, PRIORITY=ROUTINE, VERSION=1, REPLICATE_COUNT=1, REPLICATE_NUMBER=0, MIN_LIMIT=0, REPORTABLE=T) and redundant copies (TEXT_ID, ENTRY, FORMATTED_ENTRY, DATE_RECEIVED=LOGIN_DATE, ASSIGNED_OPERATOR=LOGIN_BY=ENTERED_BY)', 0)
    note('Dropped columns', 'TEST / INVESTIGATION', 'Removed 100% empty columns RETEST_OF and ASSIGNABLE_CAUSE. NOTE: the Power BI measures "Retest Rate" and "Lab Error Rate" built on them always return 0%', len(T) + len(INV))
    note('Decoding', 'Results', 'Replaced LIMS codes with readable labels (analysis codes, sample types, T/F -> TRUE/FALSE, usernames -> full names); original Analysis_Code kept for traceability', len(res))
    note('Nulls', 'Results', 'Replaced structural blanks with explicit labels: Product/Lot "N/A (EM Sample)" (4,320), Sampling_Point "N/A (Product Sample)" (386), Instrument "Not Recorded" (2,353)',
         int(f.PRODUCT.isna().sum() + f.SAMPLING_POINT.isna().sum() + f.INSTRUMENT.isna().sum()))
    note('Derived fields', 'Results', 'Added Result_Status, Pct_of_Action_Limit, Login_Month, TAT_Days, Past_Due_Date, Self_Reviewed, Audit_Corrections, Cleanroom_Grade with ISO class', len(res))
    missing = res[res.Missing_Reviewer].Result_ID.sort_values().astype(str)
    note('Flagged - not changed', 'Results', f'{len(missing)} results have no result reviewer ({", ".join(missing)}) but do have a review timestamp. Labeled "MISSING"; Missing_Reviewer = TRUE', len(missing))
    note('Flagged - not changed', 'Results', f'{int(res.Self_Reviewed.sum())} results ({res.Self_Reviewed.mean():.1%}) were reviewed by the same analyst who entered them (segregation-of-duties / data integrity risk). Self_Reviewed = TRUE', int(res.Self_Reviewed.sum()))
    conflict = int((f.REVIEWED_BY.notna() & f.REVIEWER.ne(f.REVIEWED_BY)).sum())
    note('Flagged - not changed', 'Results', f'Sample-level reviewer differs from result-level reviewer on {conflict:,} rows (where both are recorded) despite identical review timestamps. Result_Reviewer treated as authoritative; Sample_Reviewer kept for reference', conflict)
    note('Flagged - not changed', 'Results', f'Due dates are 3 days (EM) / 5 days (product) but the Power BI TAT measure uses a flat 4-day SLA. Both kept: TAT_Breach_4d_SLA = {int(res.TAT_Breach_4d_SLA.sum())}, Past_Due_Date = {int(res.Past_Due_Date.sum()):,}', int(res.Past_Due_Date.sum()))
    note('Flagged - not changed', 'Audit_Trail', f'{int((A.OLD_VALUE < 0).sum())} of {len(A)} audit corrections changed a result from -1 to 0 (negative CFU count is impossible; likely a "no growth" placeholder entered in error)', int((A.OLD_VALUE < 0).sum()))

    # ---- supporting tables ----
    lots = LOT.rename(columns={'LOT_NUMBER': 'Lot', 'PRODUCT': 'Product', 'MFG_DATE': 'Mfg_Date', 'RELEASED_ON': 'Released_On', 'DISPOSITION': 'Disposition'})
    note('Nulls', 'Lots', 'Blank DISPOSITION filled as "NOT RELEASED"', int(lots.Disposition.isna().sum()))
    lots['Disposition'] = lots.Disposition.fillna('NOT RELEASED')
    lots['Mfg_to_Release_Days'] = ((lots.Released_On - lots.Mfg_Date).dt.total_seconds() / 86400).round(1)
    per_lot = (res[res.Lot.str.startswith('L')].groupby('Lot')
               .agg(Samples_Tested=('Result_ID', 'size'), OOS_Results=('Is_OOS', 'sum'), Last_Sample_Login=('Login_Date', 'max')).reset_index())
    lots = lots.merge(per_lot, on='Lot', how='left')
    lots['Samples_Tested'] = lots.Samples_Tested.fillna(0).astype(int)
    lots['OOS_Results'] = lots.OOS_Results.fillna(0).astype(int)
    lots['Last_Sample_to_Release_Days'] = ((lots.Released_On - lots.Last_Sample_Login).dt.total_seconds() / 86400).round(1)
    untested = lots[lots.Samples_Tested == 0].Lot
    note('Flagged - not changed', 'Lots', f'{len(untested)} lots have no test samples: ' + ', '.join(untested), len(untested))

    invs = inv.merge(res[['Result_ID', 'Login_Date', 'Location', 'Cleanroom_Grade', 'Analysis', 'Result', 'Action_Limit', 'Units']],
                     left_on='RESULT_NUMBER', right_on='Result_ID', how='left')
    invs = invs.rename(columns={'INV_ID': 'Investigation_ID', 'PHASE': 'Phase', 'OPENED': 'Opened', 'CLOSED': 'Closed'})
    invs['CAPA_Raised'] = invs.CAPA_ID.notna()
    invs['CAPA_ID'] = invs.CAPA_ID.fillna('None')
    invs = invs[['Investigation_ID', 'Result_ID', 'Phase', 'Opened', 'Closed', 'Investigation_Days', 'CAPA_Raised', 'CAPA_ID',
                 'Login_Date', 'Location', 'Cleanroom_Grade', 'Analysis', 'Result', 'Action_Limit', 'Units']]

    audit = A.rename(columns={'RECORD_KEY': 'Result_ID', 'TABLE_NAME': 'Table', 'FIELD': 'Field', 'OLD_VALUE': 'Old_Value',
                              'NEW_VALUE': 'New_Value', 'CHANGED_ON': 'Changed_On', 'REASON': 'Reason'})
    audit['Changed_By'] = A.CHANGED_BY.map(uname)
    audit['Negative_Value_Corrected'] = audit.Old_Value < 0
    audit = audit.merge(res[['Result_ID', 'Date_Completed', 'Location', 'Analysis']], on='Result_ID', how='left')
    audit['Hours_After_Entry'] = ((audit.Changed_On - audit.Date_Completed).dt.total_seconds() / 3600).round(1)

    specs = PS.rename(columns={'SPEC_ID': 'Spec_ID', 'PRODUCT': 'Product', 'PRODUCT_GRADE': 'Grade', 'SAMPLING_POINT': 'Location',
                               'ANALYSIS': 'Analysis_Code', 'SPEC_TYPE': 'Limit_Type', 'MIN_VALUE': 'Min_Value', 'MAX_VALUE': 'Max_Value'})
    specs['Analysis'] = specs.Analysis_Code.map(ANALYSIS)
    specs['Product'] = specs.Product.fillna('N/A (EM)')
    specs['Grade'] = specs.Grade.map(GRADE).fillna('N/A')
    specs['Location'] = specs.Location.fillna('N/A')
    specs['In_Use'] = ~specs.Analysis_Code.eq('WATER_BIOBURDEN')
    note('Renaming', 'Specs', 'Column SAMPLING_POINT actually holds room codes (CR-101...) - renamed to Location', int(PS.SAMPLING_POINT.notna().sum()))
    note('Flagged - not changed', 'Specs', '2 water-system specs (WFI-LOOP-1, PURIFIED-LOOP-2) exist but no water samples are in the data. In_Use = FALSE', 2)

    ins = INS.rename(columns={'NAME': 'Instrument', 'TYPE': 'Type', 'CALIB_DUE': 'Calibration_Due'})
    ins['Results_Recorded'] = ins.Instrument.map(res.Instrument.value_counts()).fillna(0).astype(int)
    note('Flagged - not changed', 'Instruments', 'INCUBATOR-01/02 and AIR-SAMPLER-02 have zero results linked; settle plates & bioburden never record an incubator', int((ins.Results_Recorded == 0).sum()))

    users = U.rename(columns={'USER_NAME': 'Username', 'FULL_NAME': 'Full_Name'})
    return dict(Results=res, Lots=lots, Investigations=invs, Audit_Trail=audit, Specs=specs, Instruments=ins, Users=users)


DESCRIPTIONS = {
    'Result_ID': 'Unique LIMS result number (primary key)', 'Sample_ID': 'LIMS sample number', 'Test_ID': 'LIMS test number',
    'Login_Date': 'When sample was logged into LIMS', 'Login_Month': 'First day of login month (use for monthly trends)',
    'Due_Date': 'LIMS due date (EM = login+3d, Product = login+5d)', 'Date_Completed': 'Result entry / test completion',
    'Date_Reviewed': 'Result review timestamp', 'Sample_Category': 'Environmental Monitoring vs Product Release',
    'Sample_Type': 'EM - Air / EM - Surface / Product - Bioburden / Product - Endotoxin', 'Analysis': 'Readable test name',
    'Analysis_Code': 'Original LIMS analysis code', 'Location': 'Cleanroom (CR-101..104) or QC Micro Lab',
    'Cleanroom_Grade': 'EU GMP Annex 1 grade with ISO class', 'Sampling_Point': 'EM sampling site within room',
    'Product': 'Product code (product samples only)', 'Lot': 'Manufacturing lot (product samples only)',
    'Instrument': 'Instrument used, if recorded',
    'Result': 'Numeric result. Units differ by analysis - never sum/average across analyses',
    'Units': 'CFU/plate, CFU/m3, CFU/device, EU/device', 'Alert_Limit': 'Alert level', 'Action_Limit': 'Action / specification limit',
    'Pct_of_Action_Limit': 'Result / Action_Limit (1.0 = at limit). Lets you compare across analyses',
    'Result_Status': 'OOS / Action (>= action), Alert (>= alert & < action), Within Limits',
    'Is_OOS': 'Result >= action limit', 'Is_Alert': 'Result >= alert limit and < action limit',
    'Is_OOT': 'Out-of-trend flag carried over from source model', 'Is_Zero_Count': 'Result = 0 (no growth)',
    'TAT_Days': 'Turnaround: Date_Completed - Login_Date in days', 'TAT_Breach_4d_SLA': 'TAT > 4 days (original Power BI rule)',
    'Past_Due_Date': 'Completed after LIMS Due_Date', 'Analyst': 'Who entered the result',
    'Result_Reviewer': 'Who reviewed the result ("MISSING" if blank)',
    'Sample_Reviewer': 'Sample-level reviewer (conflicts with Result_Reviewer - reference only)',
    'Missing_Reviewer': 'Result has no reviewer', 'Self_Reviewed': 'Analyst = Result_Reviewer (data integrity risk)',
    'Audit_Corrections': 'Number of audit-trail changes to this result', 'Original_Entry_Before_Correction': 'Value before audit correction',
    'Investigation_ID': 'Linked OOS investigation', 'CAPA_ID': 'Linked CAPA', 'Investigation_Days': 'Investigation open-to-close days',
}


def summary(t):
    res, invs, lots, audit = t['Results'], t['Investigations'], t['Lots'], t['Audit_Trail']
    return pd.DataFrame([
        ['Source', 'MicroQC_Insight.pbix (LabWare-style LIMS export, Apr 2025 - Sep 2026)'],
        ['Results (clean)', f'{len(res):,}'], ['Samples', f'{res.Sample_ID.nunique():,}'],
        ['OOS results', f'{res.Is_OOS.sum()} ({res.Is_OOS.mean():.2%})'], ['Alert results', f'{res.Is_Alert.sum()}'],
        ['OOT results', f'{res.Is_OOT.sum()}'],
        ['Right-first-time', f'{(~(res.Is_OOS | res.Is_Alert | res.Is_OOT)).mean():.1%}'],
        ['Median TAT (days)', f'{res.TAT_Days.median():.1f}'], ['TAT breach (4-day SLA)', f'{res.TAT_Breach_4d_SLA.mean():.1%}'],
        ['Past LIMS due date', f'{res.Past_Due_Date.mean():.1%}'],
        ['Investigations / with CAPA', f'{len(invs)} / {invs.CAPA_Raised.sum()}'],
        ['Lots released', f'{(lots.Disposition == "RELEASED").sum()} of {len(lots)}'],
        ['Self-reviewed results', f'{res.Self_Reviewed.sum()} ({res.Self_Reviewed.mean():.1%})'],
        ['Audit-trail corrections', f'{len(audit)} ({audit.Negative_Value_Corrected.sum()} were negative values)'],
    ], columns=['Metric', 'Value'])


def write_workbook(t, path):
    def kind(col):
        if pd.api.types.is_bool_dtype(col): return 'TRUE/FALSE'
        if pd.api.types.is_datetime64_any_dtype(col): return 'Date/Time'
        if pd.api.types.is_integer_dtype(col): return 'Whole number'
        if pd.api.types.is_float_dtype(col): return 'Decimal'
        return 'Text'
    dd = pd.DataFrame([dict(Sheet=s, Field=c, Type=kind(df[c]), Description=DESCRIPTIONS.get(c, '') if s == 'Results' else '')
                       for s, df in t.items() for c in df.columns])
    sheets = [('README_Summary', summary(t)), *t.items(), ('Data_Dictionary', dd), ('Cleaning_Log', pd.DataFrame(log))]
    with pd.ExcelWriter(path, engine='openpyxl') as w:
        for name, df in sheets:
            df.to_excel(w, sheet_name=name, index=False)
            ws = w.sheets[name]
            ws.freeze_panes = 'A2'
            ws.auto_filter.ref = ws.dimensions
            for c in ws[1]:
                c.font = Font(bold=True, color='FFFFFF')
                c.fill = PatternFill('solid', fgColor='1F4E79')
            for i, col in enumerate(df.columns, 1):
                width = min(60, max(len(str(col)), *(len(str(v)) for v in df[col].head(200))) + 2)
                ws.column_dimensions[ws.cell(1, i).column_letter].width = width
            for row in ws.iter_rows(min_row=2):
                for c in row:
                    if hasattr(c.value, 'year'):
                        c.number_format = 'yyyy-mm-dd' if name == 'Lots' else 'yyyy-mm-dd hh:mm'


def write_dashboard_data(t, path):
    """Compact arrays for the dashboard page: lookup lists plus one short row per result."""
    res, invs, audit = t['Results'], t['Investigations'], t['Audit_Trail']
    start = res.Login_Date.min().normalize()
    dims = {k: sorted(res[k].unique()) for k in ['Location', 'Sample_Type', 'Sampling_Point', 'Analysis', 'Analyst']}
    idx = {k: {v: i for i, v in enumerate(vals)} for k, vals in dims.items()}
    day = lambda s: ((s - start).dt.total_seconds() / 86400).round(2)
    rows = []
    for r, d in zip(res.itertuples(), day(res.Login_Date)):
        flags = (r.Is_OOS << 0 | r.Is_Alert << 1 | r.Is_OOT << 2 | r.TAT_Breach_4d_SLA << 3 | r.Past_Due_Date << 4
                 | r.Self_Reviewed << 5 | r.Missing_Reviewer << 6 | (r.Audit_Corrections > 0) << 7)
        rows.append([int(r.Result_ID), float(d), idx['Location'][r.Location], idx['Sample_Type'][r.Sample_Type],
                     idx['Sampling_Point'][r.Sampling_Point], idx['Analysis'][r.Analysis], float(r.Result),
                     int(r.Alert_Limit), int(r.Action_Limit), int(flags), round(float(r.TAT_Days), 2), idx['Analyst'][r.Analyst]])
    data = {
        'start': start.strftime('%Y-%m-%d'),
        'dims': dims,
        'units': res.groupby('Analysis').Units.first().to_dict(),
        'grades': res.groupby('Location').Cleanroom_Grade.first().to_dict(),
        'fields': ['id', 'day', 'loc', 'type', 'point', 'analysis', 'result', 'alert', 'action', 'flags', 'tat', 'analyst'],
        'rows': rows,
        'investigations': [[int(i.Investigation_ID), int(i.Result_ID), i.Opened.strftime('%Y-%m-%d'), float(i.Investigation_Days),
                            None if i.CAPA_ID == 'None' else i.CAPA_ID] for i in invs.itertuples()],
        'audit': [[int(a.Result_ID), int(a.Old_Value), int(a.New_Value), a.Changed_By, a.Changed_On.strftime('%Y-%m-%d')] for a in audit.itertuples()],
        'log': [[s['Category'], s['Action'], int(s['Rows_Affected'])] for s in log],
    }
    with open(path, 'w') as fh:
        fh.write('// Generated by clean_microqc.py. Simulated LIMS data.\nwindow.MQC=' + json.dumps(data, separators=(',', ':')) + ';\n')


if __name__ == '__main__':
    pbix = sys.argv[1]
    out = os.path.dirname(os.path.abspath(__file__))
    tables = clean(load(pbix))
    write_workbook(tables, os.path.join(out, 'MicroQC_Insight_Clean.xlsx'))
    write_dashboard_data(tables, os.path.join(out, 'data.js'))
    print(summary(tables).to_string(index=False))
