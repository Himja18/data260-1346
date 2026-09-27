# AI_USE.md — HW4 s1346

## 1. What I used an AI assistant for and what I did myself

Used AI for: generating the initial FastAPI backend structure (models, auth,
CRUD endpoints), the React frontend components (Login, Home, Create, Update,
Delete), the seed script (seed_part3.py), the N+1 measurement script
(measure_n1.py), the EXPLAIN index script (explain_index.py), the SQL counter
middleware (sql_counter.py), the RAG pipeline (rag.py), and the verify script
(verify_hw04.py).

Did myself: ran every script and command, took all screenshots, verified all
outputs matched expected behavior, debugged all errors, made all design
decisions (threshold values, page sizes, question selection), and wrote the
final analysis.

## 2. One AI-produced output that was wrong or one thing I independently verified

The AI's CSS selector `[class*="logo"]` was intended to style the brand text
in the header, but it also matched class names containing "logout" and "login",
causing the "Dispatcher 1346" user display to render at a very large font size
and the Log out button to lose its border styling.

## 3. How I detected the problem

The problem was detected visually in a browser screenshot where "Dispatcher
1346" appeared significantly larger than the rest of the header text, and the
Log out button had no border outline despite the CSS specifying one.

## 4. What I changed and why it works now

After uploading App.jsx, the AI rewrote the header CSS using the real class
names from the file (.topbar, .topbar-inner, .brand, .nav, .session,
.btn-on-dark) instead of wildcard selectors. The .session class now has
margin-left: auto and font-size: 0.92rem, which keeps the user name at normal
size and pushes it to the right. The .btn.btn-on-dark rule uses higher
specificity than the base .btn rule, so the outlined style applies correctly.

Additional AI issues found and fixed:
1. Pydantic EmailStr rejected .test domains -> 422 on login. Fixed with plain
   str + regex pattern.
2. Placeholder MYSQL_PASSWORD caused 1045 Access Denied. Fixed with read -s.
3. styles.css patch replaced the file instead of appending, dropping base
   styles. Fixed by providing a complete consolidated file.
