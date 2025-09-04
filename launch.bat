@echo off
ECHO Activating virtual environment...
CALL .\.venv\Scripts\activate.bat

ECHO.
ECHO Launching bot...
python bot.py

ECHO.
ECHO The bot has been stopped. Press any key to close this window.
PAUSE > NUL
