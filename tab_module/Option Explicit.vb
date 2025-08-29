Option Explicit

Public Sub Install_Command_Map()
    Const SHEET_NAME As String = "Command_Map"
    Const TB As String = "Table_Command_CaseMap"
    Const COLS As Long = 6  ' Pattern, Action, ProfileKey, RampUpKey, RampDnKey, TargetSource

    Dim ws As Worksheet, lo As ListObject
    Dim rows As Variant, data() As Variant
    Dim i As Long, n As Long

    ' Remove any existing sheet with this table to avoid overlap/name conflicts
    On Error Resume Next
    Application.DisplayAlerts = False
    ThisWorkbook.Worksheets(SHEET_NAME).Delete
    Application.DisplayAlerts = True
    On Error GoTo 0

    ' Fresh sheet
    Set ws = ThisWorkbook.Worksheets.Add(After:=ThisWorkbook.Worksheets(ThisWorkbook.Worksheets.Count))
    ws.name = SHEET_NAME

    ' Defaults (adjust later if you like)
    rows = Array( _
      Array("Initial MW", "INITIAL_MW", "", "", "", "CompleteMW"), _
      Array("Begin dispatch load", "INITIAL_MW", "", "", "", "CompleteMW"), _
      Array("Begin declare capacity", "INITIAL_MW", "", "", "", "CompleteMW"), _
      Array("Initial cold", "PROFILE", "init_1", "", "", "None"), _
      Array("Cold start-up", "PROFILE", "cold_1", "", "", "None"), _
      Array("Warm start-up", "PROFILE", "warm_1", "", "", "None"), _
      Array("Hot start-up", "PROFILE", "hot_1", "", "", "None"), _
      Array("Load change after", "PROFILE", "hot_2", "", "", "None"), _
      Array("Actual syn", "RAMP", "", "rr_up", "rr_dn", "CompleteMW"), _
      Array("Min load after Syn", "RAMP", "", "rr_up", "rr_dn", "CompleteMW"), _
      Array("Revise capacity", "RAMP", "", "rr_up", "rr_dn", "CompleteMW"), _
      Array("Load change", "RAMP", "", "rr_up", "rr_dn", "CompleteMW"), _
      Array("Declare available", "HOLD", "", "", "", "None"), _
      Array("Trip", "TRIP", "", "", "", "None"), _
      Array("Shutdown by EVN", "SHUTDOWN", "sd", "", "", "None"), _
      Array("Shutdown by VP1", "SHUTDOWN", "sd", "", "", "None"), _
      Array("GCB open", "SHUTDOWN", "sd", "", "", "None"), _
      Array("Scheduled outage", "HOLD", "", "", "", "None"), _
      Array("Maintenance outage", "HOLD", "", "", "", "None"), _
      Array("Forced outage", "HOLD", "", "", "", "None"), _
      Array("Reserve shutdown", "SHUTDOWN", "sd", "", "", "None") _
    ) 'tạo một mảng có tên như hình
    n = UBound(rows) + 1 'đếm số dòng của mảng tên rows
    ' Build a 2-D array: headers + rows
    ReDim data(1 To n + 1, 1 To COLS)
    data(1, 1) = "Pattern":     data(1, 2) = "Action":      data(1, 3) = "ProfileKey"
    data(1, 4) = "RampUpKey":    data(1, 5) = "RampDnKey":  data(1, 6) = "TargetSource"
    For i = 0 To UBound(rows)
        data(i + 2, 1) = rows(i)(0)
        data(i + 2, 2) = rows(i)(1)
        data(i + 2, 3) = rows(i)(2)
        data(i + 2, 4) = rows(i)(3)
        data(i + 2, 5) = rows(i)(4)
        data(i + 2, 6) = rows(i)(5)
    Next i

    ' Drop the data and create the table at A1
    With ws.Range("A1").Resize(n + 1, COLS)
        .Value = data
        Set lo = ws.ListObjects.Add(xlSrcRange, .Cells, , xlYes)
    End With

    lo.name = TB
    lo.TableStyle = "TableStyleMedium2"
    lo.Range.Columns.AutoFit

    MsgBox TB & " created on sheet '" & SHEET_NAME & "' (" & n & " rows).", vbInformation
End Sub

