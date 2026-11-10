AIP WEEK 2 ALLOCATOR - WINDOWS QUICK START
========================================

1. Download the Windows package from the successful GitHub Actions build.
2. Extract the downloaded ZIP. If it contains another ZIP named
   AIP-Week2-Allocator-Windows.zip, extract that ZIP as well.
3. Keep all files together in the extracted AIP-Week2-Allocator folder.
   You can put this folder in Downloads or on your Desktop.
4. Double-click START.bat. Allow up to two minutes for the first launch.
5. Your browser opens at http://localhost:3000.
   If it does not open, type that address in your browser.
6. Download your Excel and PDF results before finishing. Your previous
   allocation session may not be preserved after closing or restarting.
7. Double-click STOP.bat when finished. Closing the browser does not stop
   the application. To use it again, double-click START.bat.

No separate Node.js, Python, VS Code or other installation is required.
Internet access is not required after downloading and extracting the package.
Uploaded information is processed locally on this laptop by the application.
Keep employee files and exported results in your approved company locations.

IF STARTUP DOES NOT WORK
-----------------------
If START.bat says the app is already running, it opens the existing app.
If it says port 8000 or 3000 is occupied, another application or another copy
is using that address. Use STOP.bat in the other app folder if applicable,
or contact the application administrator. Do not end unrelated programs.
Try STOP.bat followed by START.bat if this copy did not finish starting.

Startup details are in the logs folder beside START.bat. The main files are
launcher-error.log, supervisor.log, backend-error.log and frontend-error.log.
Review logs before sharing them with anyone.

For help, contact the AIP application administrator who supplied this package.
Give them the startup message and the BUILD-INFO.json file from this folder.

Company security policies still apply. Unsigned software may require IT
approval. Do not disable Windows security or bypass company restrictions.
