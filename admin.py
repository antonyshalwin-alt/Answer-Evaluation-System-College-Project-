import os
import tempfile
from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
from flask_mysqldb import MySQL
from werkzeug.utils import secure_filename
import nltk
from nltk.tokenize import word_tokenize
from nltk.stem import WordNetLemmatizer
from nltk.sentiment import SentimentIntensityAnalyzer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
import warnings
import pandas as pd
import io
import re
import cv2
import numpy as np
from pdf2image import convert_from_bytes
from PIL import Image

# --- TRY LOADING SPELLCHECKER ---
try:
    from spellchecker import SpellChecker

    spell = SpellChecker()
    # Add domain-specific terms so the autocorrect doesn't ruin tech words
    spell.word_frequency.load_words([
        'python', 'ram', 'recursion', 'polymorphism', 'html', 'php', 'sql', 'gui', 'api',
        'django', 'malware', 'ransomware', 'forensics', 'cloud', 'nlp', 'ocr', 'trocr',
        'opencv', 'mediapipe', 'phishing', 'algorithm', 'cyber', 'frontend', 'backend'
    ])
    HAS_SPELLCHECK = True
except ImportError:
    print("\n[!] WARNING: 'pyspellchecker' not installed. Run 'pip install pyspellchecker' for OCR autocorrect.\n")
    HAS_SPELLCHECK = False

# --- IMPORT PyMuPDF ---
try:
    import fitz  # PyMuPDF

    HAS_PYMUPDF = True
except ImportError:
    print("\n[!] CRITICAL WARNING: PyMuPDF is not installed! Run 'pip install PyMuPDF'\n")
    HAS_PYMUPDF = False

# --- FLASK CONFIGURATION ---
warnings.filterwarnings("ignore")

app = Flask(__name__)
app.secret_key = 'answer-evaluation-system-secret-key-2026'
app.template_folder = 'templates'

# MySQL Configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''  # Your MySQL Password
app.config['MYSQL_DB'] = 'teacher_part'

mysql = MySQL(app)

# --- LOAD NLP GRADING MODELS ONCE ---
sentence_model = SentenceTransformer('paraphrase-MiniLM-L6-v2')
sia_analyzer = SentimentIntensityAnalyzer()

# --- LAZY LOAD TROCR (UPGRADED TO LARGE MODEL) ---
trocr_processor = None
trocr_model = None


def get_trocr_model():
    """Loads ONLY TrOCR into the active Flask thread."""
    global trocr_processor, trocr_model
    import torch
    from transformers import TrOCRProcessor, VisionEncoderDecoderModel

    if trocr_model is None:
        print("🚀 Initializing TrOCR Engine (Large Model + Auto-Deskew Mode)...")
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        # Upgraded to large for commercial-grade reading accuracy
        trocr_processor = TrOCRProcessor.from_pretrained("microsoft/trocr-large-handwritten")
        trocr_model = VisionEncoderDecoderModel.from_pretrained("microsoft/trocr-large-handwritten").to(device)
        print(f"✅ TrOCR successfully loaded on: {device}")

    return trocr_processor, trocr_model


# --- NLP HELPER FUNCTIONS (Grading Logic) ---
def preprocess_text(text):
    if not text: return []
    tokens = word_tokenize(text)
    lemmatizer = WordNetLemmatizer()
    return [lemmatizer.lemmatize(token.lower()) for token in tokens]


def exact_match(expected, student):
    return 1 if expected.lower().strip() == student.lower().strip() else 0


def partial_match(expected, student):
    expected_tokens = set(preprocess_text(expected))
    student_tokens = set(preprocess_text(student))
    if not expected_tokens or not student_tokens: return 0
    common = expected_tokens & student_tokens
    return len(common) / max(len(expected_tokens), len(student_tokens))


def cosine_similarity_score(expected, student):
    try:
        vectorizer = TfidfVectorizer(tokenizer=preprocess_text)
        tfidf_matrix = vectorizer.fit_transform([expected, student])
        return cosine_similarity(tfidf_matrix[0], tfidf_matrix[1])[0][0]
    except:
        return 0


def sentiment_analysis(text):
    return (sia_analyzer.polarity_scores(text)['compound'] + 1) / 2


def enhanced_sentence_match(expected, student):
    emb_e = sentence_model.encode([expected])
    emb_s = sentence_model.encode([student])
    return cosine_similarity([emb_e.flatten()], [emb_s.flatten()])[0][0]


def coherence_score(expected, student):
    len_e = len(word_tokenize(expected))
    len_s = len(word_tokenize(student))
    if len_e == 0 or len_s == 0: return 0
    return min(len_e, len_s) / max(len_e, len_s)


def evaluate(expected, response, max_marks=10):
    if not response: return 0
    if expected.lower() == response.lower(): return max_marks

    scores = [
        exact_match(expected, response),
        partial_match(expected, response),
        cosine_similarity_score(expected, response),
        sentiment_analysis(response),
        enhanced_sentence_match(expected, response),
        coherence_score(expected, response)
    ]

    weights = [0.10, 0.20, 0.20, 0.05, 0.35, 0.10]
    final_score = sum(s * w for s, w in zip(scores, weights)) * max_marks
    return round(final_score, 1)


# --- PURE OPENCV + TROCR EXTRACTION (FULL COMMERCIAL PIPELINE) ---
def extract_text_pure_trocr(image):
    processor, model = get_trocr_model()
    import torch
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    full_text = ""
    img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)

    # ==========================================
    # 1. SHADOW REMOVAL (Background Division)
    # ==========================================
    bg_img = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, np.ones((21, 21), np.uint8))
    enhanced_gray = cv2.divide(gray, bg_img, scale=255)

    # ==========================================
    # 2. AUTO-DESKEWING (Rotation Correction)
    # ==========================================
    blur_deskew = cv2.GaussianBlur(enhanced_gray, (5, 5), 0)
    _, thresh_deskew = cv2.threshold(blur_deskew, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = np.column_stack(np.where(thresh_deskew > 0))

    if len(coords) > 0:
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle

        if 0.5 < abs(angle) < 15:
            (h, w) = img_cv.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            enhanced_gray = cv2.warpAffine(enhanced_gray, M, (w, h), flags=cv2.INTER_CUBIC,
                                           borderMode=cv2.BORDER_REPLICATE)

    enhanced_bgr = cv2.cvtColor(enhanced_gray, cv2.COLOR_GRAY2BGR)

    # ==========================================
    # 3. SEGMENTATION: HORIZONTAL PROJECTION
    # ==========================================
    _, binary = cv2.threshold(enhanced_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    row_hist = cv2.reduce(binary, 1, cv2.REDUCE_AVG).flatten()
    empty_threshold = 2

    lines = []
    in_line = False
    start_y = 0

    for y, value in enumerate(row_hist):
        if value > empty_threshold and not in_line:
            start_y = y
            in_line = True
        elif value <= empty_threshold and in_line:
            end_y = y
            if end_y - start_y > 15:
                lines.append((start_y, end_y))
            in_line = False

    if in_line and len(row_hist) - start_y > 15:
        lines.append((start_y, len(row_hist)))

    # ==========================================
    # 4. X-MARGIN CROPPING & NATURAL SORTING
    # ==========================================
    boxes = []
    for y1, y2 in lines:
        line_strip = binary[y1:y2, :]
        col_hist = cv2.reduce(line_strip, 0, cv2.REDUCE_AVG).flatten()
        ink_cols = np.where(col_hist > 0.5)[0]

        if len(ink_cols) > 0:
            x1 = ink_cols[0]
            x2 = ink_cols[-1]
            if x2 - x1 > 20:
                boxes.append((x1, y1, x2 - x1, y2 - y1))

    if not boxes:
        return ""

    # ==========================================
    # 5. AI READING: BATCH PROCESSING (SPEED BOOST)
    # ==========================================
    line_images = []


    for box in boxes:
        x, y, w, h = box
        # Reduce padding to keep text prominent
        pad = 4
        y1, y2 = max(0, y - pad), min(enhanced_bgr.shape[0], y + h + pad)
        x1, x2 = max(0, x - pad), min(enhanced_bgr.shape[1], x + w + pad)

        cropped_line = enhanced_bgr[y1:y2, x1:x2]
        if cropped_line.size == 0: continue

        # Change border to 5px instead of 20px
        white_padding = [255, 255, 255]
        cropped_line = cv2.copyMakeBorder(cropped_line, 5, 5, 5, 5, cv2.BORDER_CONSTANT, value=white_padding)
        pil_crop = Image.fromarray(cv2.cvtColor(cropped_line, cv2.COLOR_BGR2RGB))
        line_images.append(pil_crop)

        # Process in batches of 8
        batch_size = 8
        for i in range(0, len(line_images), batch_size):
            batch = line_images[i:i + batch_size]

            pixel_values = processor(batch, return_tensors="pt").pixel_values.to(device)

            # --- FIXED GENERATION PARAMETERS ---
            generated_ids = model.generate(
                pixel_values,
                max_new_tokens=40,  # Keep it shorter to prevent rambling
                no_repeat_ngram_size=2,  # Stops the model from repeating "1903" or looping
                early_stopping=True,
                num_beams=3  # Use beam search for higher accuracy instead of greedy decoding
            )
            generated_texts = processor.batch_decode(generated_ids, skip_special_tokens=True)

        for cleaned_text in generated_texts:
            cleaned_text = cleaned_text.strip()
            if len(cleaned_text) < 2 or cleaned_text in ["0 0", "0 1", "1 0", "0"]:
                continue

            if HAS_SPELLCHECK:
                corrected_words = []
                for word in cleaned_text.split():
                    clean_word = re.sub(r'[^\w]', '', word)
                    if clean_word.isalpha():
                        correction = spell.correction(clean_word)
                        corrected_words.append(correction if correction else word)
                    else:
                        corrected_words.append(word)
                cleaned_text = " ".join(corrected_words)

            # CRITICAL FIX: Preserve newline characters
            full_text += cleaned_text + "\n"

    return full_text + "\n"


def parse_answers_from_handwritten_pdf(file_storage):
    """
    Extract answers from uploaded PDF.
    Step 1: Try native text extraction (PyMuPDF)
    Step 2: If empty -> Run Pure OpenCV + TrOCR
    Step 3: Clean and split into question-numbered answers
    """
    answers = {}
    full_text = ""

    # ===============================
    # STEP 1: NATIVE PDF TEXT (PyMuPDF)
    # ===============================
    if HAS_PYMUPDF:
        try:
            file_storage.seek(0)
            pdf_bytes = file_storage.read()
            pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")

            for page in pdf_document:
                extracted = page.get_text()
                if extracted:
                    full_text += extracted + "\n"

            if len(full_text.strip()) > 20:
                print("✅ Native PDF text extracted successfully.")

        except Exception as e:
            print("⚠ PyMuPDF Extraction Failed:", e)

    # ===============================
    # STEP 2: PURE TROCR FALLBACK
    # ===============================
    if len(full_text.strip()) < 20:
        print("🔎 No embedded text found. Running Pure OpenCV + TrOCR Pipeline...")

        try:
            file_storage.seek(0)
            pdf_bytes = file_storage.read()

            # Convert PDF pages to images
            images = convert_from_bytes(pdf_bytes, dpi=300)

            for idx, image in enumerate(images):
                print(f"⚙️ Processing page {idx + 1}/{len(images)}...")
                page_text = extract_text_pure_trocr(image)
                full_text += page_text + "\n"

            print("✅ OCR Extraction completed.")

        except Exception as e:
            import traceback
            print("❌ OCR Execution Failed:\n", traceback.format_exc())
            return {}

    # ===============================
    # STEP 3: FINAL VALIDATION
    # ===============================
    if len(full_text.strip()) < 5:
        print("❌ No readable text found in PDF.")
        return {}

    print(f"\n========== RAW OCR TEXT ==========\n{full_text}\n==================================\n")

    # ===============================
    # STEP 4: CLEAN TEXT
    # ===============================
    # CRITICAL FIX: Only replace horizontal spaces, preserve \n
    full_text = re.sub(r'[ \t]+', ' ', full_text)
    full_text = full_text.replace('|', 'I')

    # ===============================
    # STEP 5: SPLIT BY QUESTION NUMBER
    # ===============================
    # CRITICAL FIX: Upgraded Regex that respects newlines
    pattern = re.compile(
        r'(?:^|\n)[^\w]*?(?:Q|O|0|Question|Ans|Answer|Qn)?\.?\s*([1-9lsoLSO][0-9]*)\s*[.:)\],:;-]+\s+',
        re.IGNORECASE
    )

    matches = list(pattern.finditer(full_text))

    if not matches:
        answers[1] = full_text.strip()
        print("⚠ No question numbers detected. Assigned entire text to Q1.")
        return answers

    for i in range(len(matches)):
        # Clean up OCR misread numbers (e.g., 's' -> '5')
        raw_num = matches[i].group(1).lower()
        raw_num = raw_num.replace('s', '5').replace('l', '1').replace('o', '0')

        try:
            q_num = int(raw_num)
        except ValueError:
            continue  # Skip if it still isn't a valid integer

        start = matches[i].end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)

        answer_text = full_text[start:end].strip()
        # Clean out lingering OCR garbage like stray '#' or '|' at the start of answers
        answer_text = re.sub(r'^[\#\|\!\-\"\'\s]+', '', answer_text)

        if answer_text:
            if q_num in answers:
                answers[q_num] += " " + answer_text
            else:
                answers[q_num] = answer_text

    print("✅ Final Parsed Answers:", answers)

    return answers


# --- ROUTES ---

@app.route('/')
def index():
    return render_template('Homepage.html')


# ADMIN & TEACHER ROUTES
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form['username'] == 'admin' and request.form['password'] == 'admin':
            session['admin_logged_in'] = True
            return redirect(url_for('admin_home'))
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM Admins WHERE username = %s AND password = %s",
                    (request.form['username'], request.form['password']))
        admin = cur.fetchone()
        cur.close()

        if admin:
            session['admin_logged_in'] = True
            return redirect(url_for('admin_home'))
    return render_template('adminlogin.html')


@app.route('/admin/home')
def admin_home():
    return render_template('adminhome.html') if 'admin_logged_in' in session else redirect(url_for('admin_login'))


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))


@app.route('/admin/students')
def admin_students():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM Students")
    students = cur.fetchall()
    cur.close()
    return render_template('admin_students.html', students=students)


@app.route('/admin/teachers')
def admin_teachers():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM Teachers")
    teachers = cur.fetchall()
    cur.close()
    return render_template('admin_teachers.html', teachers=teachers)


@app.route('/admin/approve_user/<usertype>/<int:user_id>/<action>')
def approve_user(usertype, user_id, action):
    table, col = ('Students', 'student_id') if usertype == 'student' else ('Teachers', 'teacher_id')
    status = 'approved' if action == 'approve' else 'rejected'
    cur = mysql.connection.cursor()
    cur.execute(f"UPDATE {table} SET status=%s WHERE {col}=%s", (status, user_id))
    mysql.connection.commit()
    cur.close()
    return redirect(url_for(f'admin_{usertype}s'))


@app.route('/admin/delete_student/<int:id>', methods=['POST'])
def delete_student(id):
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM Students WHERE student_id=%s", (id,))
    mysql.connection.commit()
    cur.close()
    return redirect(url_for('admin_students'))


@app.route('/admin/delete_teacher/<int:id>', methods=['POST'])
def delete_teacher(id):
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM Teachers WHERE teacher_id=%s", (id,))
    mysql.connection.commit()
    cur.close()
    return redirect(url_for('admin_teachers'))


@app.route('/admin/add_student', methods=['POST'])
def add_student():
    return redirect(url_for('admin_students'))


@app.route('/admin/add_teacher', methods=['GET'])
def add_teacher():
    return redirect(url_for('teacher_register'))


@app.route('/admin/view_teacher_tests/<int:teacher_id>')
def view_teacher_tests(teacher_id):
    if 'admin_logged_in' not in session: return redirect(url_for('admin_login'))
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM Tests WHERE teacher_id = %s", (teacher_id,))
    tests = cur.fetchall()
    cur.close()
    return render_template('view_teacher_tests.html', tests=tests, teacher_id=teacher_id)


@app.route('/admin/view_student_scores/<int:student_id>')
def view_student_scores(student_id):
    if 'admin_logged_in' not in session: return redirect(url_for('admin_login'))
    cur = mysql.connection.cursor()
    query = """
       SELECT sa.answer_id, sa.test_id, t.test_name, q.question_number, 
       q.question_text, ea.answer_text, sa.answer_text, sa.score
        FROM StudentAnswers sa
        JOIN Tests t ON sa.test_id = t.test_id
        JOIN Questions q ON sa.question_id = q.question_id
        JOIN ExpectedAnswers ea ON q.question_id = ea.question_id
        WHERE sa.student_id = %s
        ORDER BY q.question_number ASC
    """
    cur.execute(query, (student_id,))
    scores = cur.fetchall()
    cur.close()
    formatted_scores = [{
        'answer_id': s[0],
        'test_id': s[1],
        'test_name': s[2],
        'q_num': s[3],
        'question_text': s[4],
        'expected_answer': s[5],
        'student_answer': s[6],
        'score': s[7]
    } for s in scores]
    return render_template('student_scores.html', scores=formatted_scores)


@app.route('/admin/delete_student_score/<int:answer_id>', methods=['POST'])
def delete_student_score(answer_id):
    if 'admin_logged_in' not in session:
        return redirect(url_for('admin_login'))

    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM StudentAnswers WHERE answer_id=%s", (answer_id,))
    mysql.connection.commit()
    cur.close()

    flash("Student answer deleted successfully.", "success")

    return redirect(request.referrer)


@app.route('/admin/update_teacher/<int:teacher_id>', methods=['GET', 'POST'])
def update_teacher(teacher_id):
    return redirect(url_for('admin_teachers'))


# TEACHER ROUTES
@app.route('/teacher_register', methods=['GET', 'POST'])
def teacher_register():
    if request.method == 'POST':
        try:
            name = request.form['name']
            email = request.form['email']
            password = request.form['password']
            gender = request.form['gender']
            department = request.form['department']
            address = request.form['address']
            phone = request.form['phone']

            cur = mysql.connection.cursor()
            cur.execute("""
                INSERT INTO Teachers (name, email, password, gender, department, address, phone, status) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending')
            """, (name, email, password, gender, department, address, phone))

            mysql.connection.commit()
            cur.close()
            return render_template('teacher_login.html',
                                   error='Registration successful! Please wait for Admin approval.')
        except Exception as e:
            return render_template('teacher_register.html', error='Error: Email already exists or invalid data.')
    return render_template('teacher_register.html')


@app.route('/teacher_login', methods=['GET', 'POST'])
def teacher_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM Teachers WHERE email = %s AND password = %s", (email, password))
        teacher = cur.fetchone()
        cur.close()

        if teacher:
            if teacher[4] == 'approved':
                session['teacher_logged_in'] = True
                session['teacher_id'] = teacher[0]
                return redirect(url_for('teacher_home'))
            elif teacher[4] == 'rejected':
                return render_template('teacher_login.html', error='Account Rejected by Admin.')
            else:
                return render_template('teacher_login.html', error='Account Pending Approval.')
        else:
            return render_template('teacher_login.html', error='Invalid Email or Password')
    return render_template('teacher_login.html')


@app.route('/teacher_home', methods=['GET', 'POST'])
def teacher_home():
    if 'teacher_logged_in' not in session: return redirect(url_for('teacher_login'))
    cur = mysql.connection.cursor()
    if request.method == 'POST':
        if 'add_test_name' in request.form:
            test_name = request.form['test_name']
            test_class = request.form.get('test_class', '')
            cur.execute("INSERT INTO Tests (test_name, teacher_id, test_class) VALUES (%s, %s, %s)",
                        (test_name, session['teacher_id'], test_class))
            mysql.connection.commit()
        elif 'delete_test_name' in request.form:
            test_id = request.form['test_id']
            cur.execute("DELETE FROM Tests WHERE test_id = %s", (test_id,))
            mysql.connection.commit()
        elif 'update_test_name' in request.form:
            test_id = request.form['test_id']
            new_name = request.form['updated_test_name']
            new_class = request.form.get('updated_test_class', '')
            cur.execute("UPDATE Tests SET test_name = %s, test_class = %s WHERE test_id = %s",
                        (new_name, new_class, test_id))
            mysql.connection.commit()

    cur.execute("SELECT * FROM Tests WHERE teacher_id = %s", (session['teacher_id'],))
    tests = cur.fetchall()
    cur.close()
    return render_template('teacher_home.html', tests=tests)


@app.route('/teacher_profile', methods=['GET', 'POST'])
def teacher_profile():
    if 'teacher_logged_in' not in session: return redirect(url_for('teacher_login'))

    teacher_id = session['teacher_id']

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        department = request.form['department']
        address = request.form['address']
        password = request.form['password']

        cur = mysql.connection.cursor()
        if password:
            cur.execute("""
                UPDATE Teachers 
                SET name=%s, email=%s, phone=%s, department=%s, address=%s, password=%s 
                WHERE teacher_id=%s
            """, (name, email, phone, department, address, password, teacher_id))
        else:
            cur.execute("""
                UPDATE Teachers 
                SET name=%s, email=%s, phone=%s, department=%s, address=%s 
                WHERE teacher_id=%s
            """, (name, email, phone, department, address, teacher_id))

        mysql.connection.commit()
        cur.close()
        flash("Profile updated successfully!", "success")
        return redirect(url_for('teacher_profile'))

    cur = mysql.connection.cursor()
    cur.execute("SELECT name, email, phone, department, address, gender FROM Teachers WHERE teacher_id = %s",
                (teacher_id,))
    teacher_data = cur.fetchone()
    cur.close()

    if teacher_data:
        teacher = {
            'name': teacher_data[0],
            'email': teacher_data[1],
            'phone': teacher_data[2],
            'department': teacher_data[3],
            'address': teacher_data[4],
            'gender': teacher_data[5]
        }
    else:
        teacher = {}

    return render_template('teacher_profile.html', teacher=teacher)


@app.route('/teacher/view_test_questions/<int:test_id>', methods=['GET', 'POST'])
def view_teacher_test_questions(test_id):
    if 'teacher_logged_in' in session and request.method == 'POST':
        if 'delete_question' in request.form:
            try:
                cur = mysql.connection.cursor()
                cur.execute("DELETE FROM Questions WHERE question_id=%s", (request.form['question_id'],))
                mysql.connection.commit()
                cur.close()
                flash("Deleted", "danger")
            except:
                pass

        elif 'file' in request.files:
            try:
                df = pd.read_excel(request.files['file'])
                cur = mysql.connection.cursor()
                for i, row in df.iterrows():
                    cur.execute(
                        "INSERT INTO Questions (question_number, question_text, test_id, max_marks) VALUES (%s,%s,%s,%s)",
                        (row.get('S.No', i + 1), row['Question'], test_id, row.get('Marks', 10)))
                    cur.execute("INSERT INTO ExpectedAnswers (answer_text, question_id) VALUES (%s,%s)",
                                (row['Answer'], cur.lastrowid))
                mysql.connection.commit()
                cur.close()
                flash("Uploaded successfully", "success")
            except Exception as e:
                print(e)

    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM Questions WHERE test_id=%s ORDER BY question_number", (test_id,))
    questions = cur.fetchall()
    q_data = {}
    for q in questions:
        cur.execute("SELECT * FROM ExpectedAnswers WHERE question_id=%s", (q[0],))
        q_data[q[0]] = cur.fetchall()
    cur.close()

    return render_template('view_teacher_test_questions.html', questions=questions, question_answers=q_data,
                           teacher_id=test_id)


@app.route('/teacher_view_score')
def teacher_view_score():
    if 'teacher_logged_in' not in session: return redirect(url_for('teacher_login'))
    cur = mysql.connection.cursor()
    cur.execute("SELECT test_id, test_name FROM Tests WHERE teacher_id=%s", (session['teacher_id'],))
    tests = cur.fetchall()

    exam_data = {}
    for tid, tname in tests:
        exam_data[tname] = []
        cur.execute("SELECT DISTINCT student_id FROM StudentAnswers WHERE test_id=%s", (tid,))
        sids = cur.fetchall()

        cur.execute("SELECT question_id, max_marks FROM Questions WHERE test_id=%s", (tid,))
        qs = cur.fetchall()
        total_test_marks = sum([q[1] if q[1] else 10 for q in qs])

        for (sid,) in sids:
            cur.execute("SELECT name FROM Students WHERE student_id=%s", (sid,))
            sname = cur.fetchone()[0]
            cur.execute("SELECT score FROM StudentAnswers WHERE student_id=%s AND test_id=%s", (sid, tid))
            scores = [x[0] for x in cur.fetchall() if x[0] is not None]
            exam_data[tname].append(
                {'student_name': sname, 'total_obtained': sum(scores), 'total_max': total_test_marks, 'details': []})

    cur.close()
    return render_template('teacher_view_score.html', exam_data=exam_data)


@app.route('/teacher_logout')
def teacher_logout():
    session.pop('teacher_logged_in', None)
    return redirect(url_for('teacher_login'))


@app.route('/download_sample_excel')
def download_sample_excel():
    data = {
        'S.No': [1, 2, 3],
        'Question': ['What is Python?', 'Define RAM.', 'Explain Recursion.'],
        'Answer': ['A programming language...', 'Random Access Memory', 'Function calling itself...'],
        'Marks': [5, 2, 10]
    }
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
        worksheet = writer.sheets['Sheet1']
        worksheet.column_dimensions['A'].width = 8
        worksheet.column_dimensions['B'].width = 40
        worksheet.column_dimensions['C'].width = 40
        worksheet.column_dimensions['D'].width = 10

    output.seek(0)
    return Response(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-disposition": "attachment; filename=exam_template.xlsx"})


# STUDENT ROUTES
@app.route('/student_register', methods=['GET', 'POST'])
def student_register():
    if request.method == 'POST':
        try:
            name = request.form['name']
            email = request.form['email']
            age = request.form['age']
            gender = request.form['gender']
            rollno = request.form['rollno']
            address = request.form['address']
            cls = request.form['student_class']
            reg_no = request.form['registration_no']
            pwd = request.form['password']

            cur = mysql.connection.cursor()
            cur.execute("""
                INSERT INTO Students (name, age, gender, rollno, address, email, student_class, registration_no, password, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
            """, (name, age, gender, rollno, address, email, cls, reg_no, pwd))
            mysql.connection.commit()
            cur.close()
            return render_template('student_login.html', error='Registration Successful! Waiting for Admin Approval.')
        except Exception as e:
            return render_template('student_register.html', error=f'Error: {e}')
    return render_template('student_register.html')


@app.route('/student_login', methods=['GET', 'POST'])
def student_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM Students WHERE email=%s AND password=%s", (email, password))
        s = cur.fetchone()
        cur.close()

        if s and s[10] == 'approved':
            session['student_logged_in'] = True
            session['student_id'] = s[0]
            return redirect(url_for('student_home'))
        return render_template('student_login.html', error="Invalid or pending.")
    return render_template('student_login.html')


@app.route('/student_home')
def student_home(): return render_template('student_home.html')


@app.route('/student_profile', methods=['GET', 'POST'])
def student_profile():
    if 'student_logged_in' not in session: return redirect(url_for('student_login'))

    student_id = session['student_id']

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        age = request.form['age']
        address = request.form['address']
        password = request.form['password']

        cur = mysql.connection.cursor()
        if password:
            cur.execute("""
                UPDATE Students 
                SET name=%s, email=%s, age=%s, address=%s, password=%s 
                WHERE student_id=%s
            """, (name, email, age, address, password, student_id))
        else:
            cur.execute("""
                UPDATE Students 
                SET name=%s, email=%s, age=%s, address=%s 
                WHERE student_id=%s
            """, (name, email, age, address, student_id))

        mysql.connection.commit()
        cur.close()
        flash("Profile updated successfully!", "success")
        return redirect(url_for('student_profile'))

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT name, email, age, gender, address, student_class, rollno, registration_no 
        FROM Students WHERE student_id = %s
    """, (student_id,))
    student_data = cur.fetchone()
    cur.close()

    if student_data:
        student = {
            'name': student_data[0],
            'email': student_data[1],
            'age': student_data[2],
            'gender': student_data[3],
            'address': student_data[4],
            'student_class': student_data[5],
            'rollno': student_data[6],
            'reg_no': student_data[7]
        }
    else:
        student = {}

    return render_template('student_profile.html', student=student)


@app.route('/student_take_test', methods=['GET', 'POST'])
def student_take_test():
    if 'student_logged_in' not in session: return redirect(url_for('student_login'))
    sid = session['student_id']
    cur = mysql.connection.cursor()

    if request.method == 'POST':
        tid = request.form.get('test_id')

        # --- SCENARIO 1: PDF UPLOAD (Handwritten/Typed) ---
        if 'answer_pdf' in request.files and request.files['answer_pdf'].filename != '':
            try:
                file = request.files['answer_pdf']
                # Security Fix: Sanitizing user uploaded file names
                filename = secure_filename(file.filename)

                answers = parse_answers_from_handwritten_pdf(file)

                if not answers:
                    cur.close()
                    flash("Failed to read text from the PDF. Ensure handwriting is legible.", "danger")
                    return redirect(url_for('student_take_test'))

                cur.execute("SELECT question_id, question_number FROM Questions WHERE test_id=%s", (tid,))
                qmap = {q[1]: q[0] for q in cur.fetchall()}

                count = 0
                for qnum, text in answers.items():
                    if qnum in qmap:
                        cur.execute("DELETE FROM StudentAnswers WHERE student_id=%s AND question_id=%s",
                                    (sid, qmap[qnum]))
                        cur.execute(
                            "INSERT INTO StudentAnswers (student_id, test_id, question_id, answer_text) VALUES (%s,%s,%s,%s)",
                            (sid, tid, qmap[qnum], text))
                        count += 1
                mysql.connection.commit()
                cur.close()
                flash(f"Successfully processed {count} answers.", "success")
                return redirect(url_for('student_view_score'))
            except Exception as e:
                print("PDF ERROR:", e)
                cur.close()
                flash(f"Error processing PDF: {str(e)}", "danger")
                return redirect(url_for('student_take_test'))

        # --- SCENARIO 2: MANUAL TEXT INPUT ---
        else:
            saved_count = 0
            for key, val in request.form.items():
                if key.startswith('question_'):
                    try:
                        qid = int(key.split('_')[1])
                        cur.execute("DELETE FROM StudentAnswers WHERE student_id=%s AND test_id=%s AND question_id=%s",
                                    (sid, tid, qid))
                        cur.execute(
                            "INSERT INTO StudentAnswers (student_id, test_id, question_id, answer_text) VALUES (%s, %s, %s, %s)",
                            (sid, tid, qid, val))
                        saved_count += 1
                    except:
                        continue

            mysql.connection.commit()
            cur.close()
            if saved_count > 0:
                flash("Answers submitted successfully!", "success")
                return redirect(url_for('student_view_score'))
            else:
                flash("No answers were detected.", "warning")
                return redirect(url_for('student_take_test'))

    # GET REQUEST - FETCH TESTS
    cur.execute("SELECT student_class FROM Students WHERE student_id=%s", (sid,))
    sclass = cur.fetchone()[0]

    cur.execute("""
        SELECT t.test_id, t.test_name 
        FROM Tests t 
        WHERE t.test_class=%s 
        AND t.test_id NOT IN (
            SELECT DISTINCT test_id FROM StudentAnswers WHERE student_id = %s
        )
    """, (sclass, sid))
    tests = [{'test_id': t[0], 'test_name': t[1]} for t in cur.fetchall()]
    cur.close()

    return render_template('student_take_test.html', tests=tests)


@app.route('/student_take_test/<int:test_id>', methods=['GET'])
def student_take_test_questions(test_id):
    if 'student_logged_in' not in session: return redirect(url_for('student_login'))

    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM Tests WHERE test_id = %s", (test_id,))
    test = cur.fetchone()
    cur.execute("SELECT * FROM Questions WHERE test_id = %s ORDER BY question_number ASC", (test_id,))
    questions = cur.fetchall()
    cur.close()

    return render_template('student_take_test_questions.html', test=test, questions=questions, test_id=test_id)


@app.route('/student_view_score')
def student_view_score():
    if 'student_logged_in' not in session: return redirect(url_for('student_login'))
    sid = session['student_id']
    cur = mysql.connection.cursor()

    cur.execute("SELECT DISTINCT test_id FROM StudentAnswers WHERE student_id=%s", (sid,))
    tids = cur.fetchall()

    scores_data = []
    for (tid,) in tids:
        cur.execute("SELECT test_name FROM Tests WHERE test_id=%s", (tid,))
        tname = cur.fetchone()[0]

        cur.execute("""SELECT q.question_number, q.question_text, q.max_marks, ea.answer_text, sa.answer_text, sa.score, sa.answer_id 
                       FROM Questions q 
                       JOIN ExpectedAnswers ea ON q.question_id=ea.question_id 
                       LEFT JOIN StudentAnswers sa ON q.question_id=sa.question_id AND sa.student_id=%s
                       WHERE q.test_id=%s ORDER BY q.question_number""", (sid, tid))
        rows = cur.fetchall()

        details = []
        total = 0
        total_max = 0

        for r in rows:
            qnum, qtext, qmax, exp, act, score, ans_id = r
            if score is None and act:
                score = evaluate(exp, act, qmax if qmax else 10)
                cur.execute("UPDATE StudentAnswers SET score=%s WHERE answer_id=%s", (score, ans_id))
                mysql.connection.commit()

            score = score if score else 0
            act = act if act else "Not Answered"
            qmax = qmax if qmax else 10

            total += score
            total_max += qmax
            details.append(
                {'q_num': qnum, 'question': qtext, 'expected': exp, 'student': act, 'score': score, 'max_marks': qmax})

        scores_data.append({'test_name': tname, 'total': total, 'max': total_max, 'details': details})

    cur.close()
    return render_template('student_view_score.html', student_scores=scores_data)


@app.route('/student_logout')
def student_logout():
    session.pop('student_logged_in', None)
    return redirect(url_for('student_login'))


@app.route('/debug_ocr', methods=['GET', 'POST'])
def debug_ocr():
    if request.method == 'POST':
        if 'file' not in request.files: return "No file"
        file = request.files['file']

        # Test the parsing directly
        answers = parse_answers_from_handwritten_pdf(file)
        return f"""<h1>Debug Results</h1><pre>{answers}</pre><br><a href='/debug_ocr'>Back</a>"""

    return """<form method='post' enctype='multipart/form-data'><input type='file' name='file'><input type='submit'></form>"""


if __name__ == '__main__':
    app.run(debug=True)