import os
from flask import Flask, render_template, request, redirect, url_for, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

# --- 1. Flask 및 설정 초기화 ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_strong_secret_key' 
# SQLite 데이터베이스 파일 경로 설정
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///imageshare.db' 
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 이미지 저장 폴더 설정
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True) # 폴더가 없으면 생성
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

db = SQLAlchemy(app)

# --- 2. 데이터베이스 모델 정의 ---

# 이미지와 태그를 연결하는 중간 테이블 (다대다 관계)
image_tags = db.Table('image_tags',
    db.Column('image_id', db.Integer, db.ForeignKey('image.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'), primary_key=True)
)

# Image 모델 (이미지 정보 저장)
class Image(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(100), nullable=False)
    # relationship: 이 이미지에 연결된 모든 태그를 가져옴
    tags = db.relationship('Tag', secondary=image_tags, lazy='subquery',
                           backref=db.backref('images', lazy=True))

# Tag 모델 (태그 이름 저장)
class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)


# --- 3. 데이터베이스 생성 (서버 시작 시 실행) ---
with app.app_context():
    db.create_all()

# ----------------------------------------------------
# --- 4. 라우트 (Route) 정의 ---
# ----------------------------------------------------

# --- A. 메인 페이지 및 이미지 업로드 처리 (필수 기능 1, 2) ---
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # 파일 확인
        if 'file' not in request.files:
            return redirect(request.url)
        file = request.files['file']
        tags_input = request.form.get('tags', '')

        if file.filename == '':
            return redirect(request.url)

        if file:
            filename = secure_filename(file.filename)
            # 1. 파일을 서버의 'uploads' 폴더에 저장
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

            # 2. 파일 정보를 데이터베이스에 저장
            new_image = Image(filename=filename)
            db.session.add(new_image) # SAWarning 해결을 위해 태그 처리 전 추가

            # 3. 태그 처리 및 연결
            tag_names = [name.strip().lower() for name in tags_input.split(',') if name.strip()]
            
            for tag_name in tag_names:
                # 기존 태그를 찾거나, 없으면 새로 생성
                tag = Tag.query.filter_by(name=tag_name).first()
                if not tag:
                    tag = Tag(name=tag_name)
                    db.session.add(tag)
                # 이미지와 태그 연결
                new_image.tags.append(tag)
            
            db.session.commit()
            return redirect(url_for('index'))

    # GET 요청: 모든 이미지 목록을 가져와서 템플릿에 전달
    all_images = Image.query.all()
    return render_template('index.html', images=all_images)

# --- B. 태그 검색 기능 (필수 기능 3) ---
@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('query')
    
    if not query:
        return redirect(url_for('index'))

    # 검색어를 개별 태그로 분리
    search_tags = [name.strip().lower() for name in query.split(',') if name.strip()]
    
    # 1. 검색된 태그를 DB에서 찾기
    tags_to_find = Tag.query.filter(Tag.name.in_(search_tags)).all()
    tag_ids = [tag.id for tag in tags_to_find]

    if not tag_ids:
        found_images = []
    else:
        # 2. 태그 ID를 통해 연결된 이미지를 찾기 (AND 검색이 아닌 OR 검색: 하나라도 일치하면 표시)
        found_images = Image.query \
            .join(Image.tags) \
            .filter(Tag.id.in_(tag_ids)) \
            .distinct() \
            .all()

    return render_template('index.html', images=found_images, search_query=query)

# --- C. 업로드된 파일 제공 라우트 (BuildError 해결) ---
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    # uploads 폴더에서 파일을 찾아서 사용자에게 보여줍니다.
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# --- 5. 서버 실행 ---
if __name__ == '__main__':
    app.run(debug=True)