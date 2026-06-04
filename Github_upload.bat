@echo off
chcp 65001 > nul

echo ===================================================
echo  Comic_reader GitHub アップロード
echo ===================================================

git config --global --add safe.directory //100.96.86.9/nas/ProgramProject/Comic_reader

echo [1/3] 変更されたファイルをスキャン中...
git add .

echo ---------------------------------------------------
set msg=
set /p msg="Comment (Enter to skip): "

if "%msg%"=="" (
    set msg=Update: %date% %time:~0,5%
)
echo ---------------------------------------------------

echo [2/3] 変更を記録中: "%msg%"
git commit -m "%msg%"

echo [3/3] GitHubへアップロード中...
git push

echo ===================================================
echo  完了しました！画面を閉じるには何かキーを押してください。
echo ===================================================
pause
