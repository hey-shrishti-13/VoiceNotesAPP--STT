This is a Flask based web application that lets users record their voice, transcribe the speech, translate it to English and save it as a note. Users can also view all saved notes, search them, rename or delete them, and download both text and audio files.

The app works like this: you open the main page, click on Start Recording, speak in Hindi or English and then click Stop Recording. The application will process the audio, show the original text, show the English translation and then open a small popup to let you enter a name and choose a category like Personal, Office or Others before saving. After saving, you can go to the Saved Notes page to see all your notes, play the audio, read the transcription, download it as TXT or DOCX, rename it or delete it. You can also search by name or text and filter by category.

The project uses Flask for the backend, HTML CSS and JavaScript for the frontend and SQLite as the database. The browser SpeechRecognition API is used for live transcription while recording. Audio is uploaded to the backend for processing and translation.

To run the app, make sure you have Python installed. Install the required packages with pip install flask and pip install python-docx. Then run python app.py and open [http://127.0.0.1:5000/](http://127.0.0.1:5000/) in your browser.

The project folder contains a static folder for CSS, a templates folder for HTML files (index.html for the main page and list\_notes.html for the saved notes page), an app.py file for the backend code and a documents.db SQLite database file.
