Attribute VB_Name = "EMReport"
'==========================================================================
' Environmental Monitoring QC Trend Report - weekly report macro
' Author: Dennis Nguyen (portfolio project, synthetic data)
' Import: Alt+F11 > File > Import File... then save workbook as .xlsm
'==========================================================================
Option Explicit

'Build the weekly EM summary: copy one week of results to the Weekly sheet,
'total excursions by room, highlight Action results, and export a PDF.
Public Sub BuildWeeklyReport()
    Dim src As ListObject, wk As Worksheet, ans As String
    Dim weekEnd As Date, weekStart As Date
    Dim r As ListRow, outRow As Long, i As Long
    Dim rooms As Object, key As Variant, status As String
    Dim pdfPath As String

    ans = InputBox("Week ending (yyyy-mm-dd):", "Weekly EM report", _
                   Format(Application.WorksheetFunction.Max( _
                   ThisWorkbook.Worksheets("RawData").ListObjects("tblEM").ListColumns("Date").DataBodyRange), "yyyy-mm-dd"))
    If ans = "" Then Exit Sub
    If Not IsDate(ans) Then MsgBox "Not a valid date.", vbExclamation: Exit Sub
    weekEnd = CDate(ans)
    weekStart = weekEnd - 6

    Application.ScreenUpdating = False
    Set src = ThisWorkbook.Worksheets("RawData").ListObjects("tblEM")
    Set wk = ThisWorkbook.Worksheets("Weekly")
    wk.Cells.Clear

    wk.Range("A1").Value = "Weekly EM Report: " & Format(weekStart, "mmm d") & " - " & Format(weekEnd, "mmm d, yyyy")
    wk.Range("A1").Font.Bold = True: wk.Range("A1").Font.Size = 14
    wk.Range("A3:G3").Value = Array("SampleID", "Date", "Room", "SampleType", "CFU", "Limit hit", "Analyst")
    wk.Range("A3:G3").Font.Bold = True

    Set rooms = CreateObject("Scripting.Dictionary")
    outRow = 4
    For Each r In src.ListRows
        With r.Range
            If .Cells(1, 2).Value >= weekStart And .Cells(1, 2).Value <= weekEnd Then
                status = .Cells(1, 10).Value
                If Not rooms.Exists(.Cells(1, 3).Value) Then rooms.Add .Cells(1, 3).Value, Array(0, 0, 0)
                key = rooms(.Cells(1, 3).Value)
                key(0) = key(0) + 1
                If status = "Alert" Then key(1) = key(1) + 1
                If status = "Action" Then key(2) = key(2) + 1
                rooms(.Cells(1, 3).Value) = key
                If status <> "Pass" Then          'list only excursions in detail
                    wk.Cells(outRow, 1).Resize(1, 7).Value = Array(.Cells(1, 1).Value, .Cells(1, 2).Value, _
                        .Cells(1, 3).Value, .Cells(1, 5).Value, .Cells(1, 6).Value, status, .Cells(1, 7).Value)
                    wk.Cells(outRow, 2).NumberFormat = "yyyy-mm-dd"
                    If status = "Action" Then wk.Cells(outRow, 1).Resize(1, 7).Interior.Color = RGB(248, 203, 173)
                    If status = "Alert" Then wk.Cells(outRow, 1).Resize(1, 7).Interior.Color = RGB(255, 230, 153)
                    outRow = outRow + 1
                End If
            End If
        End With
    Next r
    If outRow = 4 Then wk.Cells(4, 1).Value = "No excursions this week.": outRow = 5

    'Room summary block to the right
    wk.Range("I3:M3").Value = Array("Room", "Samples", "Alerts", "Actions", "Excursion %")
    wk.Range("I3:M3").Font.Bold = True
    i = 4
    For Each key In rooms.Keys
        wk.Cells(i, 9).Resize(1, 4).Value = Array(key, rooms(key)(0), rooms(key)(1), rooms(key)(2))
        wk.Cells(i, 13).Formula = "=IFERROR((K" & i & "+L" & i & ")/J" & i & ",0)"
        wk.Cells(i, 13).NumberFormat = "0.0%"
        i = i + 1
    Next key
    wk.Columns("A:M").AutoFit
    Application.ScreenUpdating = True

    If rooms.Count = 0 Then MsgBox "No samples found for that week.", vbExclamation: Exit Sub

    pdfPath = ThisWorkbook.Path & Application.PathSeparator & "EM_weekly_" & Format(weekEnd, "yyyy-mm-dd") & ".pdf"
    wk.PageSetup.Orientation = xlLandscape
    wk.PageSetup.Zoom = False
    wk.PageSetup.FitToPagesWide = 1
    wk.PageSetup.FitToPagesTall = False
    wk.ExportAsFixedFormat Type:=xlTypePDF, Filename:=pdfPath
    wk.Activate
    MsgBox "Weekly report built and saved to:" & vbCrLf & pdfPath, vbInformation
End Sub
