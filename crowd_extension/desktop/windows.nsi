Unicode true
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "WinVer.nsh"
!include "x64.nsh"
Name "众包采集"
OutFile "${OUTPUT}"
InstallDir "$LOCALAPPDATA\Programs\FoodCrowd"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 16
ShowInstDetails nevershow
Page instfiles
UninstPage uninstConfirm
UninstPage instfiles
!insertmacro MUI_LANGUAGE "SimpChinese"

Function .onInit
  ${IfNot} ${AtLeastWin10}
    MessageBox MB_ICONSTOP "本程序需要 Windows 10 或 11。"
    Abort
  ${EndIf}
  ${If} ${RunningX64}
    SetRegView 64
  ${Else}
    MessageBox MB_ICONSTOP "本安装包需要 64 位 Windows。请联系邀请人取得匹配的安装包。"
    Abort
  ${EndIf}
  IfFileExists "$INSTDIR\*" 0 ready
  ClearErrors
  FileOpen $0 "$INSTDIR\.foodcrowd-install" r
  IfErrors unsafe 0
  FileRead $0 $1
  FileClose $0
  StrCmp $1 "foodcrowd-v4" ready 0
  unsafe:
    MessageBox MB_ICONSTOP "安装目录已有其他文件。请联系邀请人处理，安装不会覆盖它们。"
    Abort
  ready:
FunctionEnd

Section "安装"
  SetShellVarContext current
  SetOutPath "$INSTDIR"
  File /r "${PAYLOAD}/*"
  FileOpen $0 "$INSTDIR\.foodcrowd-install" w
  FileWrite $0 "foodcrowd-v4"
  FileClose $0
  WriteUninstaller "$INSTDIR\卸载众包采集.exe"
  WriteRegStr HKCU "Software\Classes\foodcrowd" "" "众包采集邀请"
  WriteRegStr HKCU "Software\Classes\foodcrowd" "URL Protocol" ""
  WriteRegStr HKCU "Software\Classes\foodcrowd\shell\open\command" "" '"$INSTDIR\众包采集.exe" "%1"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FoodCrowd" "DisplayName" "众包采集"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FoodCrowd" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FoodCrowd" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FoodCrowd" "UninstallString" '"$INSTDIR\卸载众包采集.exe"'
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FoodCrowd" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FoodCrowd" "NoRepair" 1
  CreateShortCut "$DESKTOP\众包采集.lnk" "$INSTDIR\众包采集.exe"
  CreateShortCut "$SMPROGRAMS\众包采集.lnk" "$INSTDIR\众包采集.exe"
SectionEnd

Function .onInstSuccess
  Exec '"$INSTDIR\众包采集.exe"'
FunctionEnd

Section "Uninstall"
  SetShellVarContext current
  SetRegView 64
  ClearErrors
  FileOpen $0 "$INSTDIR\.foodcrowd-install" r
  IfErrors unsafe 0
  FileRead $0 $1
  FileClose $0
  StrCmp $1 "foodcrowd-v4" 0 unsafe
  ReadRegStr $0 HKCU "Software\Classes\foodcrowd\shell\open\command" ""
  StrCmp $0 '"$INSTDIR\众包采集.exe" "%1"' 0 keep_protocol
    DeleteRegKey HKCU "Software\Classes\foodcrowd"
  keep_protocol:
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\FoodCrowd"
  Delete "$DESKTOP\众包采集.lnk"
  Delete "$SMPROGRAMS\众包采集.lnk"
  RMDir /r "$INSTDIR"
  Goto done
  unsafe:
    MessageBox MB_ICONSTOP "无法确认安装目录，已停止卸载，文件没有删除。"
    Abort
  done:
SectionEnd
