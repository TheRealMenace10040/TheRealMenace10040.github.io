Attribute VB_Name = "VendorTracker"
'==========================================================================
' Lab Supply & Vendor Performance Tracker - automation macros
' Author: Dennis Nguyen (portfolio project, synthetic data)
' Import: Alt+F11 > File > Import File... then save workbook as .xlsm
'==========================================================================
Option Explicit

'Recalculate everything, sort reorder alerts so "YES" rows are on top,
'and stamp the refresh time on the dashboard.
Public Sub RefreshAll_And_Stamp()
    Dim lo As ListObject
    Application.ScreenUpdating = False
    Application.CalculateFull

    Set lo = ThisWorkbook.Worksheets("ReorderAlerts").ListObjects("tblReorder")
    With lo.Sort
        .SortFields.Clear
        .SortFields.Add Key:=lo.ListColumns("Reorder?").DataBodyRange, Order:=xlDescending
        .SortFields.Add Key:=lo.ListColumns("SuggestedQty").DataBodyRange, Order:=xlDescending
        .Header = xlYes
        .Apply
    End With

    ThisWorkbook.Worksheets("Dashboard").Range("B11").Value = Format(Now, "yyyy-mm-dd hh:nn")
    Application.ScreenUpdating = True
    MsgBox ThisWorkbook.Worksheets("Dashboard").Range("B8").Value & _
           " item(s) need reordering; " & _
           ThisWorkbook.Worksheets("Dashboard").Range("B10").Value & _
           " lot(s) expiring within 30 days.", vbInformation, "Refresh complete"
End Sub

'Write every item flagged "YES" to a dated CSV next to the workbook
'so purchasing can paste it straight into a requisition.
Public Sub ExportReorderList()
    Dim lo As ListObject, r As ListRow, f As Integer, path As String, n As Long
    Set lo = ThisWorkbook.Worksheets("ReorderAlerts").ListObjects("tblReorder")
    path = ThisWorkbook.Path & Application.PathSeparator & _
           "reorder_" & Format(Date, "yyyy-mm-dd") & ".csv"

    f = FreeFile
    Open path For Output As #f
    Print #f, "SKU,Description,VendorID,UsableQty,MinStock,OpenPOQty,SuggestedQty"
    For Each r In lo.ListRows
        If r.Range.Cells(1, lo.ListColumns("Reorder?").Index).Value = "YES" Then
            Print #f, r.Range.Cells(1, 1).Value & ",""" & r.Range.Cells(1, 2).Value & """," & _
                      r.Range.Cells(1, 3).Value & "," & r.Range.Cells(1, 4).Value & "," & _
                      r.Range.Cells(1, 5).Value & "," & r.Range.Cells(1, 6).Value & "," & _
                      r.Range.Cells(1, 8).Value
            n = n + 1
        End If
    Next r
    Close #f
    MsgBox n & " item(s) exported to:" & vbCrLf & path, vbInformation, "Reorder list"
End Sub

'Append PO rows from a CSV (PO,SKU,OrderDate,PromisedDate,ReceivedDate,Qty).
'Formula columns (vendor, cost, lead time, on-time) are copied from the row above.
Public Sub ImportPOs()
    Dim fileName As Variant, f As Integer, lineText As String, parts() As String
    Dim lo As ListObject, nr As ListRow, added As Long, skipped As Long

    fileName = Application.GetOpenFilename("CSV files (*.csv),*.csv", , "Select PO export")
    If fileName = False Then Exit Sub
    Set lo = ThisWorkbook.Worksheets("PurchaseOrders").ListObjects("tblPOs")

    f = FreeFile
    Open fileName For Input As #f
    Line Input #f, lineText                       'skip header
    Do While Not EOF(f)
        Line Input #f, lineText
        parts = Split(lineText, ",")
        If UBound(parts) < 5 Then
            skipped = skipped + 1
        ElseIf Not lo.ListColumns("PO").DataBodyRange.Find(parts(0), LookAt:=xlWhole) Is Nothing Then
            skipped = skipped + 1                 'duplicate PO number
        Else
            Set nr = lo.ListRows.Add
            nr.Range.Cells(1, 1).Value = parts(0)
            nr.Range.Cells(1, 2).Value = parts(1)
            nr.Range.Cells(1, 4).Value = CDate(parts(2))
            nr.Range.Cells(1, 5).Value = CDate(parts(3))
            If Len(parts(4)) > 0 Then nr.Range.Cells(1, 6).Value = CDate(parts(4))
            nr.Range.Cells(1, 7).Value = CLng(parts(5))
            CopyFormulasFromRowAbove nr, Array(3, 8, 9, 10, 11, 12, 13)
            added = added + 1
        End If
    Loop
    Close #f
    MsgBox added & " PO(s) added, " & skipped & " skipped (duplicate or malformed).", vbInformation
End Sub

'Copy R1C1 formulas from the previous table row into the given columns.
Private Sub CopyFormulasFromRowAbove(nr As ListRow, cols As Variant)
    Dim c As Variant
    If nr.Index < 2 Then Exit Sub
    For Each c In cols
        nr.Range.Cells(1, c).FormulaR1C1 = nr.Range.Cells(0, c).FormulaR1C1
    Next c
End Sub
