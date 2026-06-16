# Nukki

Nukki는 이미지의 흰색 배경을 제거하거나, 스캔한 이미지처럼 글자와 외곽선을 강조해 투명 PNG/JPEG로 저장하는 Windows GUI 프로그램입니다.

## 주요 기능

- 아이콘/그림의 바깥 흰 배경 제거
- 스캔 이미지 만들기 모드
- 여러 이미지 일괄 처리
- 영역별 배경 제거 및 영역명 기반 저장
- 저장 이름 일괄 지정: `로고(1)`, `로고(2)` 형식
- PNG 투명 출력 또는 JPEG 출력

## 실행

```powershell
python nukki_ui.py
```

## 빌드

PyInstaller로 Windows 실행 파일을 생성한 뒤, 변경 사항이 있으면 자동으로 `origin/main`에 커밋하고 push합니다.

```powershell
.\build_nukki_exe.bat
```

빌드 결과는 `dist\Nukki\Nukki.exe`에 생성됩니다.

빌드 없이 GitHub에만 반영하려면 다음 스크립트를 사용할 수 있습니다.

```powershell
.\deploy_to_git.bat "Update Nukki project"
```
