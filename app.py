import os
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename

# --- 1. Flask 및 설정 초기화 ---
app = Flask(__name__)
# 세션 사용을 위한 SECRET_KEY는 필수입니다.
app.config['SECRET_KEY'] = 'your_strong_secret_key' 
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///imageshare.db' 
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 이미지 저장 폴더 설정
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True) 
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 관리자 인증 코드 정의
ADMIN_CODE = '072409'

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
            db.session.add(new_image) 

            # 3. 태그 처리 및 연결
            tag_names = [name.strip().lower() for name in tags_input.split(',') if name.strip()]
            
            for tag_name in tag_names:
                tag = Tag.query.filter_by(name=tag_name).first()
                if not tag:
                    tag = Tag(name=tag_name)
                    db.session.add(tag)
                new_image.tags.append(tag)
            
            db.session.commit()
            return redirect(url_for('index'))

    # GET 요청: 모든 이미지 목록을 가져와서 템플릿에 전달
    all_images = Image.query.all()
    # 세션에서 관리자 상태를 가져와 템플릿에 전달
    is_admin = session.get('is_admin', False) 
    return render_template('index.html', images=all_images, is_admin=is_admin)

# --- B. 태그 검색 기능 (필수 기능 3) ---
@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('query')
    
    if not query:
        return redirect(url_for('index'))

    search_tags = [name.strip().lower() for name in query.split(',') if name.strip()]
    
    tags_to_find = Tag.query.filter(Tag.name.in_(search_tags)).all()
    tag_ids = [tag.id for tag in tags_to_find]

    if not tag_ids:
        found_images = []
    else:
        # 하나라도 일치하는 이미지를 검색합니다.
        found_images = Image.query \
            .join(Image.tags) \
            .filter(Tag.id.in_(tag_ids)) \
            .distinct() \
            .all()

    is_admin = session.get('is_admin', False)
    return render_template('index.html', images=found_images, search_query=query, is_admin=is_admin)

# --- C. 업로드된 파일 제공 라우트 ---
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- D. 관리자 인증 라우트 ---
@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        entered_code = request.form.get('code')
        if entered_code == ADMIN_CODE:
            session['is_admin'] = True
            return redirect(url_for('index'))
        else:
            return render_template('admin_login.html', error='잘못된 인증 코드입니다.')
    
    # GET 요청 처리: 이미 관리자라면 권한 해제 페이지로
    if session.get('is_admin'):
        # 관리자 권한 해제 버튼 기능 (로그아웃 역할)
        session.pop('is_admin', None) 
        return redirect(url_for('index'))
        
    return render_template('admin_login.html')

# --- E. 사진 삭제 기능 (관리자 전용) ---
@app.route('/delete_image/<int:image_id>', methods=['POST'])
def delete_image(image_id):
    # 관리자 인증 확인
    if not session.get('is_admin'):
        return "관리자 권한이 없습니다.", 403 

    image_to_delete = Image.query.get_or_404(image_id)
    
    # 1. 실제 파일 삭제
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], image_to_delete.filename)
    if os.path.exists(file_path):
        os.remove(file_path)

    # 2. 데이터베이스에서 정보 삭제
    db.session.delete(image_to_delete)
    db.session.commit()

    return redirect(request.referrer or url_for('index')) # 삭제 후 이전 페이지로 돌아가기

# --- 5. 서버 실행 ---
if __name__ == '__main__':
    app.run(debug=True)
