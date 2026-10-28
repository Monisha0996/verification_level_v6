"""AZM training prototype. No genuine card processing, KYC, or Sumsub/Ottu API calls."""
import os, sqlite3, secrets, hashlib, hmac, uuid
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from PIL import Image, ImageOps, UnidentifiedImageError

BASE = Path(__file__).parent
DATA_DIR = Path(os.getenv('AZM_DATA_DIR', str(BASE)))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB = Path(os.getenv('AZM_DB_PATH', str(DATA_DIR/'azm_demo.sqlite3')))
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))
# Render requires a persistent SECRET_KEY environment variable to preserve sessions across restarts.
app.config.update(MAX_CONTENT_LENGTH=3*1024*1024, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.getenv('HTTPS_ONLY')=='1')
IMAGE_DIR = DATA_DIR/'demo_card_uploads'; IMAGE_DIR.mkdir(parents=True, exist_ok=True)

def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def db():
    conn=sqlite3.connect(DB);conn.row_factory=sqlite3.Row; conn.execute('PRAGMA foreign_keys=ON');return conn

def init_db():
    with db() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'client', applicant_id TEXT UNIQUE, created_at TEXT);
        CREATE TABLE IF NOT EXISTS cards(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), cardholder TEXT NOT NULL, bin_digits TEXT NOT NULL, last4 TEXT NOT NULL, expiry TEXT NOT NULL, image_path TEXT, action_id TEXT UNIQUE NOT NULL, check_id TEXT UNIQUE NOT NULL, status TEXT NOT NULL DEFAULT 'pending', reviewed_at TEXT, admin_comment TEXT DEFAULT '', gateway_token TEXT UNIQUE, created_at TEXT);
        CREATE TABLE IF NOT EXISTS deposits(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), card_id INTEGER NOT NULL REFERENCES cards(id), amount REAL NOT NULL, status TEXT NOT NULL DEFAULT 'initiated', ottu_session TEXT UNIQUE NOT NULL, reference TEXT UNIQUE NOT NULL, created_at TEXT, paid_at TEXT, credit_status TEXT NOT NULL DEFAULT 'not_credited', checkout_mode TEXT, checkout_match TEXT DEFAULT 'not_checked');''')
    with db() as c:
        columns={x['name'] for x in c.execute('PRAGMA table_info(deposits)').fetchall()}
        if 'checkout_mode' not in columns:c.execute('ALTER TABLE deposits ADD COLUMN checkout_mode TEXT')
        if 'checkout_match' not in columns:c.execute("ALTER TABLE deposits ADD COLUMN checkout_match TEXT DEFAULT 'not_checked'")
    with db() as c:
        if not c.execute("SELECT id FROM users WHERE role='admin'").fetchone():
            pwd=os.getenv('ADMIN_PASSWORD','ChangeMe123!')
            c.execute('INSERT INTO users(name,email,password,role,applicant_id,created_at) VALUES(?,?,?,?,?,?)',('Demo Admin',os.getenv('ADMIN_EMAIL','admin@azm.local'),generate_password_hash(pwd),'admin','admin_app',now()))
init_db()

def csrf():
    if 'csrf' not in session: session['csrf']=secrets.token_urlsafe(32)
    return session['csrf']
app.jinja_env.globals['csrf_token']=csrf
@app.before_request
def csrf_verify():
    if request.method=='POST' and not hmac.compare_digest(str(session.get('csrf','')),str(request.form.get('csrf',''))):abort(400,'Invalid CSRF token')

def login_required(role=None):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args,**kwargs):
            if not session.get('uid'):return redirect(url_for('login'))
            if role and session.get('role')!=role:abort(403)
            return fn(*args,**kwargs)
        return wrapped
    return decorator

def current_user():
    with db() as c:return c.execute('SELECT * FROM users WHERE id=?',(session['uid'],)).fetchone()

@app.route('/')
def home():return redirect(url_for('admin') if session.get('role')=='admin' else url_for('dashboard') if session.get('uid') else url_for('login'))
@app.route('/register',methods=['GET','POST'])
def register():
    if request.method=='POST':
        name=request.form.get('name','').strip();email=request.form.get('email','').strip().lower();password=request.form.get('password','')
        if len(name)<2 or '@' not in email or len(password)<10:flash('Please provide a name, valid email and password with at least 10 characters.','error')
        else:
            try:
                with db() as c:c.execute('INSERT INTO users(name,email,password,role,applicant_id,created_at) VALUES(?,?,?,?,?,?)',(name,email,generate_password_hash(password),'client','demo_app_'+uuid.uuid4().hex[:12],now()))
                flash('Registered. Your simulated Sumsub KYC profile has been created.','success');return redirect(url_for('login'))
            except sqlite3.IntegrityError:flash('Email already registered.','error')
    return render_template('register.html')
@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        with db() as c:u=c.execute('SELECT * FROM users WHERE email=?',(request.form.get('email','').strip().lower(),)).fetchone()
        if u and check_password_hash(u['password'],request.form.get('password','')):
            session.clear();session['uid']=u['id'];session['role']=u['role'];csrf();return redirect(url_for('home'))
        flash('Incorrect credentials.','error')
    return render_template('login.html')
@app.post('/logout')
def logout():session.clear();return redirect(url_for('login'))
@app.route('/client')
@login_required('client')
def dashboard():
    with db() as c:
        cards=c.execute('SELECT * FROM cards WHERE user_id=? ORDER BY id DESC',(session['uid'],)).fetchall()
        deposits=c.execute('SELECT d.*,c.last4,c.cardholder FROM deposits d JOIN cards c ON c.id=d.card_id WHERE d.user_id=? ORDER BY d.id DESC',(session['uid'],)).fetchall()
    return render_template('client.html',user=current_user(),cards=cards,deposits=deposits, pending_amount=session.get('pending_deposit_amount'))

def clean_image(file):
    if not file or not file.filename:raise ValueError('Choose a card image.')
    try:
        img=Image.open(file.stream);img.verify();file.stream.seek(0);img=Image.open(file.stream)
        if img.format not in ('PNG','JPEG'):raise ValueError('Only JPEG or PNG are supported.')
        img=ImageOps.exif_transpose(img)
        if img.width*img.height>15_000_000:raise ValueError('Image too large.')
        img=img.convert('RGB');img.thumbnail((1200,1200))
        dest=uuid.uuid4().hex+'.jpg';img.save(IMAGE_DIR/dest,format='JPEG',quality=80)
        return dest
    except (UnidentifiedImageError,OSError):raise ValueError('Invalid image. Upload JPEG or PNG.')
@app.route('/cards/new',methods=['GET','POST'])
@login_required('client')
def add_card():
    if request.method=='POST':
        try:
            img=clean_image(request.files.get('image'))
            # Sumsub MOCK accepts only a fabricated image. Real collection happens
            # in Sumsub's SDK and CRM receives only reviewed outcomes/references.
            with db() as c:
                user=c.execute('SELECT name FROM users WHERE id=?',(session['uid'],)).fetchone()
                c.execute('INSERT INTO cards(user_id,cardholder,bin_digits,last4,expiry,image_path,action_id,check_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
                    (session['uid'],user['name'],'','','',img,'demo_action_'+uuid.uuid4().hex[:12],'demo_check_'+uuid.uuid4().hex[:12],now()))
            flash('New card image submitted for Sumsub-style approval. After admin approval, return to Make a deposit and select this new card to continue to Ottu.','success')
            return redirect(url_for('dashboard'))
        except ValueError as e:flash(str(e),'error')
    return render_template('add_card.html')
@app.post('/deposits/new')
@login_required('client')
def create_deposit():
    try:amount=float(request.form.get('amount',''))
    except (TypeError,ValueError):abort(400)
    if not (1<=amount<=100000):flash('Demo amount must be AED 1–100,000.','error');return redirect(url_for('dashboard'))
    supplied=request.form.get('card_id','').strip()
    if supplied=='new_card':
        # A new payment method always requires its own verification action.
        # Preserve only the deposit amount in the session; no card credentials.
        session['pending_deposit_amount']=amount
        flash('New card selected. Upload a dummy image for Sumsub-style review before Ottu checkout.','success')
        return redirect(url_for('add_card'))
    with db() as c:
        supplied=request.form.get('card_id','').strip()
        if supplied:
            try:card_id=int(supplied)
            except ValueError:abort(400)
            card=c.execute("SELECT * FROM cards WHERE id=? AND user_id=? AND status='approved'",(card_id,session['uid'])).fetchone()
        else:
            # First payment: automatically use the latest approved image evidence.
            # If no unbound item remains, select an existing saved card.
            card=c.execute("SELECT * FROM cards WHERE user_id=? AND status='approved' AND gateway_token IS NULL ORDER BY id DESC LIMIT 1",(session['uid'],)).fetchone()
            if not card:
                card=c.execute("SELECT * FROM cards WHERE user_id=? AND status='approved' AND gateway_token IS NOT NULL ORDER BY id DESC LIMIT 1",(session['uid'],)).fetchone()
        if not card:
            flash('Upload dummy card evidence and obtain approval first.','error')
            return redirect(url_for('dashboard'))
        ref='AZM-'+uuid.uuid4().hex[:10].upper();sid='mock_ottu_'+uuid.uuid4().hex[:14]
        cur=c.execute('INSERT INTO deposits(user_id,card_id,amount,ottu_session,reference,created_at) VALUES(?,?,?,?,?,?)',(session['uid'],card['id'],amount,sid,ref,now()))
        dep_id=cur.lastrowid
    session.pop('pending_deposit_amount',None)
    return redirect(url_for('checkout',deposit_id=dep_id))
@app.route('/checkout/<int:deposit_id>')
@login_required('client')
def checkout(deposit_id):
    with db() as c:dep=c.execute('SELECT d.*,c.last4,c.cardholder,c.gateway_token FROM deposits d JOIN cards c ON c.id=d.card_id WHERE d.id=? AND d.user_id=?',(deposit_id,session['uid'])).fetchone()
    if not dep:abort(404)
    return render_template('checkout.html',dep=dep)
@app.post('/checkout/<int:deposit_id>/simulate')
@login_required('client')
def checkout_simulate(deposit_id):
    # TRAINING ONLY. Never accept a real PAN or CVV here; an actual Ottu hosted
    # page collects credentials on the payment provider's infrastructure.
    result=request.form.get('result')
    mode=request.form.get('mode')
    if result not in ('paid','failed') or mode not in ('new','saved'):abort(400)
    with db() as c:
        dep=c.execute('SELECT d.*,c.status AS card_status,c.gateway_token,c.cardholder,c.bin_digits,c.last4,c.expiry FROM deposits d JOIN cards c ON c.id=d.card_id WHERE d.id=? AND d.user_id=?',(deposit_id,session['uid'])).fetchone()
        if not dep:abort(404)
        if dep['status']!='initiated':flash('This payment already has a result.','error');return redirect(url_for('dashboard'))
        if dep['card_status']!='approved':abort(403)
        if mode=='saved':
            # Only a demo confirmation marker reaches Flask. Never receive, log,
            # persist, or validate an actual CVV in AZM's backend.
            if request.form.get('demo_cvv_entered') != '1':
                flash('Enter the dummy security code for the saved card before continuing.','error')
                return redirect(url_for('checkout',deposit_id=deposit_id))
            if not dep['gateway_token']:
                flash('No saved Ottu token yet. Use the new-card checkout first.','error');return redirect(url_for('checkout',deposit_id=deposit_id))
            matched='mock_saved_token_bound'
        else:
            holder=' '.join(request.form.get('cardholder','').split())
            bin_digits=request.form.get('bin_digits','').strip()
            last4=request.form.get('last4','').strip()
            expiry=request.form.get('expiry','').strip()
            valid=(len(holder)>=2 and bin_digits.isdigit() and len(bin_digits) in (6,8) and
                   last4.isdigit() and len(last4)==4 and len(expiry)==5 and expiry[2]=='/' and
                   expiry[:2].isdigit() and 1<=int(expiry[:2])<=12 and expiry[3:].isdigit())
            # DEMO ONLY: capture fictional masked metadata at simulated Ottu,
            # and compare cardholder against KYC as a weak illustrative signal.
            # In production the PSP/SDK must make a reliable card-to-check binding;
            # do not use name/BIN/last4 alone for automatic ownership approval.
            if not valid or holder.casefold()!=' '.join(dep['cardholder'].split()).casefold():
                c.execute("UPDATE deposits SET status='held_verification',checkout_mode='new',checkout_match='name_or_format_mismatch',credit_status='not_credited' WHERE id=?",(deposit_id,))
                flash('Demo checkout information did not match the client name or test format. Deposit held.','error')
                return redirect(url_for('dashboard'))
            matched='illustrative_name_check_only_not_ownership_proof'
        if result=='paid':
            token=dep['gateway_token'] or 'mock_tok_'+uuid.uuid4().hex[:16]
            if mode=='new':
                c.execute('UPDATE cards SET gateway_token=?,cardholder=?,bin_digits=?,last4=?,expiry=? WHERE id=?',
                          (token,holder,bin_digits,last4,expiry,dep['card_id']))
            else:
                c.execute('UPDATE cards SET gateway_token=? WHERE id=?',(token,dep['card_id']))
            c.execute("UPDATE deposits SET status='paid',checkout_mode=?,checkout_match=?,paid_at=?,credit_status='credited_demo' WHERE id=?",(mode,matched,now(),deposit_id))
            flash('SIMULATED Ottu payment success and MT5 credit. No real money moved.','success')
        else:
            c.execute("UPDATE deposits SET status='failed',checkout_mode=?,checkout_match=?,credit_status='not_credited' WHERE id=?",(mode,matched,deposit_id))
            flash('Simulated Ottu payment declined.','error')
    return redirect(url_for('dashboard'))
@app.route('/admin')
@login_required('admin')
def admin():
    with db() as c:
        cards=c.execute('SELECT c.*,u.name AS client,u.applicant_id FROM cards c JOIN users u ON u.id=c.user_id ORDER BY c.id DESC').fetchall()
        deposits=c.execute('SELECT d.*,u.name AS client,c.last4 FROM deposits d JOIN users u ON u.id=d.user_id JOIN cards c ON c.id=d.card_id ORDER BY d.id DESC').fetchall()
        users=c.execute("SELECT * FROM users WHERE role='client' ORDER BY id DESC").fetchall()
    return render_template('admin.html',cards=cards,deposits=deposits,users=users)
@app.post('/admin/cards/<int:card_id>/review')
@login_required('admin')
def review(card_id):
    status=request.form.get('status');note=request.form.get('comment','').strip()[:500]
    if status not in ('approved','rejected'):abort(400)
    with db() as c:
        card=c.execute('SELECT * FROM cards WHERE id=?',(card_id,)).fetchone()
        if not card:abort(404)
        c.execute("UPDATE cards SET status=?,reviewed_at=?,admin_comment=?,gateway_token=CASE WHEN ?='rejected' THEN NULL ELSE gateway_token END WHERE id=?",(status,now(),note,status,card_id))
    flash('Simulated Sumsub decision recorded by demo admin.','success');return redirect(url_for('admin'))
@app.route('/admin/cards/<int:card_id>/image')
@login_required('admin')
def admin_image(card_id):
    from flask import send_file
    with db() as c:card=c.execute('SELECT image_path FROM cards WHERE id=?',(card_id,)).fetchone()
    if not card or not card['image_path']:abort(404)
    return send_file(IMAGE_DIR/Path(card['image_path']).name,mimetype='image/jpeg',as_attachment=False)
@app.route('/architecture')
def architecture():return render_template('architecture.html')
@app.route('/notes')
def implementation_notes():return render_template('notes.html')
if __name__=='__main__':app.run(debug=False,port=5000)
