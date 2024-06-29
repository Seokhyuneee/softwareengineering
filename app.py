from flask import Flask, render_template, request, session, redirect, url_for, jsonify
import sqlite3 as db
import pandas as pd
import random
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # 세션을 사용하기 위해 필요한 비밀 키

# 데이터베이스 연결
conn = db.connect('data.db', check_same_thread=False)
c = conn.cursor()

# 데이터프레임으로 사용자와 영화 데이터 불러오기
def load_data():
    global user_df, movie_df
    user_df = pd.read_sql_query("SELECT * FROM user", conn)
    movie_df = pd.read_sql_query("SELECT * FROM movie", conn)

load_data()

# 로그인 함수
def log_in(id: str, pw: str):
    c.execute('SELECT id, pw FROM user WHERE id = ? AND pw = ?', (id, pw))
    rr = c.fetchone()
    if rr is None:
        return False, "아이디 또는 비밀번호가 올바르지 않습니다."
    else:
        return True, "로그인 성공"

# 회원가입 함수
def register(id: str, pw: str, confirm_pw: str, age: int):
    if pw != confirm_pw:
        return False, "비밀번호와 비밀번호 확인 값이 일치하지 않습니다."
    
    if age < 1 or age > 999:
        return False, "나이 값이 올바르지 않습니다."
    
    try:
        c.execute('SELECT id FROM user WHERE id = ?', (id,))
        if c.fetchone():
            return False, "이미 사용 중인 아이디입니다."
        
        c.execute('INSERT INTO user (id, pw, age) VALUES (?, ?, ?)', (id, pw, age))
        conn.commit()
        return True, "회원가입 성공"
    except db.Error as e:
        return False, f"데이터베이스 오류: {str(e)}"

def del_from_list(id, title):
    title = title + ', '
    c.execute('SELECT * FROM user WHERE id = ?', (id, ))
    getList = c.fetchone()[3]
    newList = getList.replace(title, '')
    c.execute('UPDATE user SET likelist = ? WHERE id = ?', (newList, id))
    conn.commit()

def add_to_list(id, title):
    title = title + ', '
    c.execute('SELECT * FROM user WHERE id = ?', (id, ))
    getList = c.fetchone()[3]
    newList = getList + title
    c.execute('UPDATE user SET likelist = ? WHERE id = ?', (newList, id))
    conn.commit()

def recommend_movies(user_id, keywords=None):
    load_data()
    
    user = user_df[user_df['id'] == user_id].iloc[0]
    user_age = user['age']
    user_likelist = user['likelist'].strip(',').split(', ') if user['likelist'] else []

    suitable_movies = movie_df[movie_df['rating'] <= user_age]

    if keywords:
        keywords = [kw.strip() for kw in keywords.split(',')]
    else:
        keywords = []

    def filter_movies_by_keywords(movies, keywords):
        if not keywords:
            return movies
        return movies[movies.apply(lambda x: any(keyword.lower() in x['title'].lower().split() or keyword.lower() in x['description'].lower().split() for keyword in keywords), axis=1)]

    def count_keyword_matches(description, keywords):
        count = 0
        for keyword in keywords:
            if keyword.lower() in description.lower().split():
                count += 1
        return count

    def highlight_keywords(text, keywords):
        for keyword in keywords:
            text = text.replace(keyword, f'<span style="color: red;">{keyword}</span>')
        return text

    if not user_likelist and keywords:
        keyword_movies = filter_movies_by_keywords(suitable_movies, keywords)

        if not keyword_movies.empty:
            keyword_movies['keyword_matches'] = keyword_movies['description'].apply(lambda desc: count_keyword_matches(desc, keywords))
            keyword_movies = keyword_movies.sort_values(by='keyword_matches', ascending=False)
            keyword_movies['description'] = keyword_movies['description'].apply(lambda desc: highlight_keywords(desc, keywords))
            recommended_movies = keyword_movies.head(10)
            return recommended_movies
        else:
            random_movies = suitable_movies.sample(n=10)
            return random_movies

    elif user_likelist and keywords:
        liked_movies = movie_df[movie_df['title'].isin(user_likelist)]
        liked_descriptions = liked_movies['description'].tolist()

        keyword_movies = filter_movies_by_keywords(suitable_movies, keywords)

        if not keyword_movies.empty:
            keyword_movies['keyword_matches'] = keyword_movies['description'].apply(lambda desc: count_keyword_matches(desc, keywords))
            keyword_movies = keyword_movies.sort_values(by='keyword_matches', ascending=False)
            keyword_movies['description'] = keyword_movies['description'].apply(lambda desc: highlight_keywords(desc, keywords))
            recommended_movies = keyword_movies.head(10)
            return recommended_movies
        else:
            return pd.DataFrame({"title": ["입력한 키워드에 해당하는 영화가 없습니다."]})

    elif not user_likelist and not keywords:
        return suitable_movies.sample(n=10)

    else:
        liked_movies = movie_df[movie_df['title'].isin(user_likelist)]
        liked_descriptions = liked_movies['description'].tolist()

        if len(liked_descriptions) > 0 and len(suitable_movies) > 0:
            vectorizer = TfidfVectorizer().fit_transform(liked_descriptions + suitable_movies['description'].tolist())
            vectors = vectorizer.toarray()
            liked_vectors = vectors[:len(liked_descriptions)]
            movie_vectors = vectors[len(liked_descriptions):]

            similarity_matrix = cosine_similarity(liked_vectors, movie_vectors)
            similarity_scores = similarity_matrix.max(axis=0)

            top_indices = similarity_scores.argsort()[-10:][::-1]
            recommended_movies = suitable_movies.iloc[top_indices]
            return recommended_movies
        else:
            return suitable_movies.sample(n=10)

@app.route('/', methods=['GET', 'POST'])
def index():
    login_error = ""
    signup_error = ""
    
    if request.method == 'POST':
        if 'loginUsername' in request.form:
            username = request.form['loginUsername']
            password = request.form['loginPassword']
            success, message = log_in(username, password)
            if success:
                session['username'] = username
                return redirect('/movie_index')
            else:
                login_error = message
        elif 'signupUsername' in request.form:
            username = request.form['signupUsername']
            password = request.form['signupPassword']
            confirm_password = request.form['confirmPassword']
            age = int(request.form['age'])
            success, message = register(username, password, confirm_password, age)
            if success:
                session['username'] = username
                return redirect('/')
            else:
                signup_error = message
                return render_template('index.html', login_error=login_error, signup_error=signup_error, show_signup_form=True)
    
    return render_template('index.html', login_error=login_error, signup_error=signup_error, show_signup_form=False)


@app.route('/movie_index', methods=['GET', 'POST'])
def movie_index():
    user_id = session['username']
    keyword = request.form.get('keyword') if request.method == 'POST' else session.get('keyword')
    if request.method == 'POST':
        session['keyword'] = keyword
    recommendations = recommend_movies(user_id, keyword)
    user = user_df[user_df['id'] == user_id].iloc[0]
    user_likelist = user['likelist'].strip(',').split(', ') if user['likelist'] else []
    return render_template('movie_index.html', recommendations=recommendations, user_likelist=user_likelist)

@app.route('/my_list')
def my_list():
    user_id = session['username']
    user = user_df[user_df['id'] == user_id].iloc[0]
    user_likelist = user['likelist'].strip(',').split(', ') if user['likelist'] else []
    session['last_page'] = request.referrer
    if user_likelist:
        my_list_movies = movie_df[movie_df['title'].isin(user_likelist)]
        return render_template('my_list.html', my_list_movies=my_list_movies if not my_list_movies.empty else None)
    else:
        return render_template('my_list.html', my_list_movies=None)

@app.route('/movie/<title>')
def movie(title):
    user_id = session['username']
    user = user_df[user_df['id'] == user_id].iloc[0]
    user_likelist = user['likelist'].strip(',').split(', ') if user['likelist'] else []
    movie = movie_df[movie_df['title'] == title].iloc[0]
    is_liked = title in user_likelist
    session['last_page'] = url_for('movie_index')
    return render_template('movie.html', movie=movie, is_liked=is_liked)

@app.route('/back')
def back():
    last_page = session.get('last_page', url_for('movie_index'))
    if 'my_list' in last_page:
        return redirect(url_for('my_list'))
    elif 'movie_index' in last_page:
        return redirect(url_for('movie_index'))
    return redirect(last_page)

@app.route('/toggle_like', methods=['POST'])
def toggle_like():
    user_id = session['username']
    title = request.json['title']
    is_liked = request.json['is_liked']

    if is_liked:
        add_to_list(user_id, title)
    else:
        del_from_list(user_id, title)

    return jsonify(success=True)

if __name__ == '__main__':
    app.run(debug=True)
