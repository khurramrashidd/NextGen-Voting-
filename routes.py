import os
import uuid
import hashlib
import random
from datetime import datetime
from functools import wraps

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, session,
    current_app, send_from_directory, jsonify, abort
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# Import models
from models import (
    db, Voter, Candidate, Vote, Admin, BoothOfficer,
    BallotStatus, MismatchLog, Nomination, DigiLockerDummy, CandidateUser
)

# Import utils and Blockchain
from utils import save_face_image, encode_face_from_file, compare_faces
from blockchain import BlockchainUtils

main_bp = Blueprint('main', __name__)

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
ECI_USERNAME = "eci"
ECI_PASSWORD = "eci123"

# ---------------- Helpers ----------------
def allowed_file(filename):
    if not filename:
        return False
    ext = filename.rsplit('.', 1)[-1].lower()
    return ext in ALLOWED_EXTENSIONS

def ensure_upload_folder():
    upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
    if not os.path.isabs(upload_folder):
        upload_folder = os.path.join(current_app.root_path, upload_folder)
    os.makedirs(upload_folder, exist_ok=True)
    current_app.config['UPLOAD_FOLDER'] = upload_folder
    return upload_folder

def ensure_admin_exists():
    admin = Admin.query.filter_by(username='admin').first()
    if not admin:
        admin = Admin(username='admin')
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()

def require_eci(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get('eci') and session.get('role') != 'admin':
            flash('Please login as ECI to access this page', 'warning')
            return redirect(url_for('main.eci_login'))
        return func(*args, **kwargs)
    return wrapper

def activate_ballot_for_voter(voter_id, booth_number='B1', note='auto'):
    BallotStatus.query.filter_by(voter_id=voter_id, booth_number=booth_number, is_active=True).update({'is_active': False})
    bs = BallotStatus(voter_id=voter_id, booth_number=booth_number, is_active=True, timestamp=datetime.utcnow())
    db.session.add(bs)
    db.session.commit()
    return bs

# ---------------- Startup ----------------
@main_bp.before_request
def startup_checks():
    if getattr(current_app, 'startup_checked', False):
        return
    try:
        ensure_upload_folder()
        ensure_admin_exists()
    except Exception:
        pass
    current_app.startup_checked = True

@main_bp.route("/", methods=["GET"])
def index():
    return render_template("index.html")

# ---------------- Live Results & Stats API ----------------
@main_bp.route('/results')
def results_page():
    return render_template('result.html')

@main_bp.route('/api/live_stats')
def api_live_stats():
    total_votes = Vote.query.count()
    votes = Vote.query.all()
    candidates = Candidate.query.all()
    
    candidate_tally = {c.candidate_id: 0 for c in candidates}
    party_tally = {}
    
    for v in votes:
        if v.candidate_id in candidate_tally:
            candidate_tally[v.candidate_id] += 1
        else:
            candidate_tally[v.candidate_id] = 1 

    results_list = []
    for c in candidates:
        count = candidate_tally.get(c.candidate_id, 0)
        party = c.party
        party_tally[party] = party_tally.get(party, 0) + count
        
        results_list.append({
            'name': c.name,
            'party': c.party,
            'constituency': c.constituency,
            'state': c.state,
            'count': count
        })
        
    party_list = [{'party': k, 'count': v} for k, v in party_tally.items()]
    party_list.sort(key=lambda x: x['count'], reverse=True)
    results_list.sort(key=lambda x: x['count'], reverse=True)

    return jsonify({
        'total_votes': total_votes,
        'candidates': results_list,
        'parties': party_list
    })

# ---------------- Candidate Nomination ----------------
@main_bp.route("/candidates", methods=["GET", "POST"])
def candidates():
    if request.method == "POST":
        try:
            aadhaar = request.form["aadhaar"]
            if Nomination.query.filter_by(aadhaar=aadhaar).first():
                flash("❌ A nomination with this Aadhaar already exists.", "danger")
                return redirect(url_for("main.candidate_dashboard"))

            files = {}
            for f in ["affidavit", "property_cert", "education_cert", "criminal_record"]:
                file = request.files.get(f)
                if file and file.filename:
                    filename = secure_filename(file.filename)
                    upload_folder = ensure_upload_folder()
                    file.save(os.path.join(upload_folder, filename))
                    files[f] = filename
                else:
                    files[f] = None

            new_nom = Nomination(
                name=request.form["name"],
                dob=request.form["dob"],
                aadhaar=aadhaar,
                address=request.form["address"],
                party=request.form["party"],
                constituency=request.form["constituency"],
                state=request.form.get("state", "Unknown"),
                email=request.form["email"],
                phone=request.form["phone"],
                affidavit=files["affidavit"],
                property_cert=files["property_cert"],
                education_cert=files["education_cert"],
                criminal_record=files["criminal_record"],
                status="Pending",
                username=aadhaar,
                password=generate_password_hash("candidate123")
            )
            db.session.add(new_nom)
            db.session.commit()
            flash("✅ Your nomination has been successfully submitted to the ECI for review.", "success")
            return redirect(url_for("main.candidate_dashboard"))
        except Exception as e:
            db.session.rollback()
            flash(f"❌ Failed: {str(e)}", "danger")
    return render_template("candidates.html")

@main_bp.route("/api/digilocker/<aadhaar>", methods=["GET"])
def api_digilocker_get(aadhaar):
    record = DigiLockerDummy.query.filter_by(aadhaar=str(aadhaar)).first()
    if not record: return jsonify({"found": False}), 404
    return jsonify({
        "found": True, "name": record.name, "dob": record.dob, "aadhaar": record.aadhaar,
        "address": record.address, "party": record.party, "constituency": record.constituency,
        "email": record.email, "phone": record.phone
    })

# ---------------- Candidate Auth ----------------
@main_bp.route("/candidate_signup", methods=["GET", "POST"])
def candidate_signup():
    if request.method == "POST":
        aadhaar = request.form["aadhaar"]
        password = request.form["password"]
        if CandidateUser.query.filter_by(aadhaar=aadhaar).first():
            flash("Aadhaar already registered", "danger")
            return redirect(url_for("main.candidate_signup"))
        cand = CandidateUser(aadhaar=aadhaar)
        cand.set_password(password)
        db.session.add(cand)
        db.session.commit()
        flash("Signup successful! Please login.", "success")
        return redirect(url_for("main.candidate_login"))
    return render_template("candidate_signup.html")

@main_bp.route("/candidate_login", methods=["GET", "POST"])
def candidate_login():
    if request.method == "POST":
        aadhaar = request.form["aadhaar"]
        password = request.form["password"]
        cand = CandidateUser.query.filter_by(aadhaar=aadhaar).first()
        if cand and cand.check_password(password):
            session["candidate_id"] = cand.id
            flash("Login successful", "success")
            return redirect(url_for("main.candidate_dashboard"))
        else:
            flash("Invalid Aadhaar or password", "danger")
    return render_template("candidate_login.html")

@main_bp.route("/candidate_dashboard")
def candidate_dashboard():
    if "candidate_id" not in session: return redirect(url_for("main.candidate_login"))
    cand = CandidateUser.query.get(session["candidate_id"])
    nomination = Nomination.query.filter_by(aadhaar=cand.aadhaar).first()
    return render_template("candidate_dashboard.html", cand=cand, nomination=nomination)

@main_bp.route("/candidate_logout")
def candidate_logout():
    session.pop("candidate_id", None)
    return redirect(url_for("main.index"))

# ---------------- ECI Admin ----------------
@main_bp.route("/login_choice")
def login_choice(): return render_template("login_choice.html")

@main_bp.route("/eci_login", methods=["GET", "POST"])
def eci_login():
    if request.method == "POST":
        if request.form.get("username") == ECI_USERNAME and request.form.get("password") == ECI_PASSWORD:
            session.clear()
            session['eci'] = True
            session['role'] = 'eci'
            flash('Logged in as ECI', 'success')
            return redirect(url_for('main.eci_dashboard'))
        flash('Invalid ECI credentials', 'danger')
    return render_template('eci_login.html')

@main_bp.route("/eci_dashboard")
def eci_dashboard():
    if not session.get('eci'): return redirect(url_for('main.eci_login'))
    candidates = Nomination.query.order_by(Nomination.created_at.desc()).all()
    return render_template("eci_dashboard.html", candidates=candidates)

@main_bp.route("/eci/view/<int:id>")
@require_eci
def eci_view_candidate(id):
    cand = Nomination.query.get_or_404(id)
    return render_template("eci_view.html", candidate=cand)

@main_bp.route("/approve/<int:id>", methods=["POST", "GET"])
@require_eci
def approve_candidate(id):
    cand = Nomination.query.get_or_404(id)
    cand.status = "Approved"
    cand.reviewed_at = datetime.utcnow()
    cand.reviewed_by = session.get('role') or 'eci'
    cand.rejection_reason = None
    
    existing_c = Candidate.query.filter_by(candidate_id=cand.aadhaar).first()
    if not existing_c:
        new_c = Candidate(candidate_id=cand.aadhaar, name=cand.name, party=cand.party, constituency=cand.constituency, state=cand.state)
        db.session.add(new_c)
    db.session.commit()
    flash(f"Candidate {cand.name} approved and added to ballot.", "success")
    return redirect(url_for("main.eci_dashboard"))

@main_bp.route("/reject/<int:id>", methods=["POST"])
@require_eci
def reject_candidate(id):
    cand = Nomination.query.get_or_404(id)
    reason = request.form.get("reason", "Documents invalid")
    cand.status = "Rejected"
    cand.rejection_reason = reason
    cand.reviewed_at = datetime.utcnow()
    cand.reviewed_by = session.get('role') or 'eci'
    public_c = Candidate.query.filter_by(candidate_id=cand.aadhaar).first()
    if public_c: db.session.delete(public_c)
    db.session.commit()
    flash(f"Candidate rejected: {reason}", "warning")
    return redirect(url_for("main.eci_dashboard"))

# ---------------- Voter Signup/Login ----------------
@main_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form.get('name')
        dob = request.form.get('dob')
        aadhaar = request.form.get('aadhaar')
        voter_id = request.form.get('voter_id')
        face = request.files.get('face')

        if Voter.query.filter((Voter.voter_id == voter_id) | (Voter.aadhaar == aadhaar)).first():
            flash('Voter ID or Aadhaar already exists', 'danger')
            return redirect(url_for('main.signup'))

        face_path = None
        if face:
            try: face_path = save_face_image(face, voter_id)
            except: face_path = None

        try:
            states = ["Maharashtra", "Delhi", "UP", "Karnataka", "Bihar"]
            state = random.choice(states)
            voter = Voter(
                name=name, dob=datetime.strptime(dob, '%Y-%m-%d').date(), aadhaar=aadhaar, voter_id=voter_id, face_image=face_path,
                father_name=f"Father of {name}", gender=random.choice(["Male", "Female"]),
                address=f"House {random.randint(10, 999)}, Sector {random.randint(1, 20)}, {state}",
                assembly=f"AC-{random.randint(1, 200)} {state}", part_no=f"Part-{random.randint(1, 50)}", serial_no=f"SL-{random.randint(1, 1200)}"
            )
            db.session.add(voter)
            db.session.commit()
            flash('Signup successful. Details auto-fetched.', 'success')
            return redirect(url_for('main.index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating voter: {str(e)}', 'danger')
            return redirect(url_for('main.signup'))
    return render_template('signup.html')

@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        role = request.form.get('role')
        username = request.form.get('username')
        password = request.form.get('password')
        if role == 'admin':
            admin = Admin.query.filter_by(username=username).first()
            if admin and admin.check_password(password):
                session.clear()
                session['role'] = 'admin'
                return redirect(url_for('main.admin_dashboard'))
        elif role == 'booth':
            booth = BoothOfficer.query.filter_by(username=username).first()
            if booth and booth.check_password(password):
                session.clear()
                session['role'] = 'booth'
                session['booth_number'] = booth.booth_number
                return redirect(url_for('main.booth_dashboard'))
        elif role == 'voter':
            voter = Voter.query.filter_by(voter_id=username).first()
            if voter:
                session.clear()
                session['role'] = 'voter'
                session['voter_id'] = voter.voter_id
                return redirect(url_for('main.voter_dashboard'))
        flash('Invalid credentials', 'danger')
    return render_template('login.html')

@main_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('main.index'))

@main_bp.route('/voter_dashboard')
def voter_dashboard():
    if session.get('role') != 'voter': return redirect(url_for('main.login'))
    voter = Voter.query.filter_by(voter_id=session.get('voter_id')).first()
    return render_template('voter_dashboard.html', voter=voter)

# ---------------- Face Scan & Voting ----------------
@main_bp.route('/voter_face_scan')
def voter_face_scan_page(): return render_template('voter_face_scan.html')

@main_bp.route('/api/face_scan', methods=['POST'])
def api_face_scan():
    booth_number = request.form.get('booth_number') or 'B1'
    file = request.files.get('face')
    if not file: return jsonify({'status': 'error', 'message': 'face image required'}), 400
    tmp_name = secure_filename(f"tmp_{uuid.uuid4().hex}.jpg")
    upload_folder = ensure_upload_folder()
    tmp_path = os.path.join(upload_folder, tmp_name)
    file.save(tmp_path)
    matched_voter = None
    voters = Voter.query.all()
    try:
        unknown_enc = encode_face_from_file(tmp_path)
        if unknown_enc is not None:
            for voter in voters:
                if not voter.face_image: continue
                try:
                    known_enc = encode_face_from_file(voter.face_image)
                    if known_enc is not None and compare_faces(known_enc, unknown_enc):
                        matched_voter = voter
                        break
                except: pass
    except: pass
    try: os.remove(tmp_path)
    except: pass
    if matched_voter:
        voter_hash = hashlib.sha256(matched_voter.voter_id.encode()).hexdigest()
        existing_vote = Vote.query.filter_by(voter_hash=voter_hash).first()
        if existing_vote: return jsonify({'status': 'error', 'message': f'❌ ERROR: {matched_voter.name} has ALREADY VOTED.', 'activate': False})
        activate_ballot_for_voter(matched_voter.voter_id, booth_number, note='face-verified')
        return jsonify({'status': 'ok', 'message': f'✅ Welcome {matched_voter.name}. Ballot activated', 'activate': True})
    try:
        ml = MismatchLog(aadhaar='', voter_id='', note='FACE_MISMATCH', timestamp=datetime.utcnow())
        db.session.add(ml); db.session.commit()
    except: pass
    return jsonify({'status': 'mismatch', 'message': '❌ No match found.', 'activate': False})

@main_bp.route('/manual_override', methods=['POST'])
def manual_override():
    aadhaar = request.form.get('aadhaar')
    voter_id = request.form.get('voter_id')
    booth_number = request.form.get('booth_number') or 'B1'
    note = request.form.get('note') or 'Manual override'
    activate_ballot_for_voter(voter_id, booth_number, note=note)
    ml = MismatchLog(aadhaar=aadhaar or '', voter_id=voter_id, note=f"OVERRIDE: {note}", timestamp=datetime.utcnow())
    db.session.add(ml); db.session.commit()
    flash('Ballot activated manually.', 'success')
    return redirect(url_for('main.booth_dashboard'))

@main_bp.route('/api/manual_override', methods=['POST'])
def api_manual_override():
    data = request.get_json() or {}
    voter_id = data.get('voter_id')
    booth_number = data.get('booth_number') or 'B1'
    activate_ballot_for_voter(voter_id, booth_number, note="API Override")
    return jsonify({'status': 'ok', 'message': 'Ballot activated'})

@main_bp.route('/ballot_machine_viewer/<booth_number>')
def ballot_machine_page(booth_number): return render_template('ballot_machine.html', booth_number=booth_number)

@main_bp.route('/api/poll_ballot/<booth_number>')
def api_poll_ballot(booth_number):
    active = BallotStatus.query.filter_by(booth_number=booth_number, is_active=True).first()
    if not active: return jsonify({'active': False})
    voter = Voter.query.filter_by(voter_id=active.voter_id).first()
    db_candidates = Candidate.query.all()
    
    # Generate JSON with Dynamic Logo URLs
    cands_json = []
    for c in db_candidates:
        cands_json.append({
            'candidate_id': c.candidate_id, 'name': c.name, 'party': c.party,
            'constituency': c.constituency or "General", 'details': "Official Candidate",
            'logo_url': f"https://ui-avatars.com/api/?name={c.party.replace(' ', '+')}&background=random&color=fff&size=128",
            'social_link': '#'
        })
    
    # Dummy Filler with Logos
    if len(cands_json) < 20:
        parties = ["Tech Future", "Green Earth", "Youth Voice", "Digital Front", "Urban Reform"]
        for i in range(len(cands_json), 25):
            p = random.choice(parties)
            cands_json.append({
                'candidate_id': f'DUMMY_{i}', 'name': f'Candidate {chr(65+i)}', 'party': p,
                'constituency': 'General', 'details': 'Independent Candidate',
                'logo_url': f"https://ui-avatars.com/api/?name={p.replace(' ', '+')}&background=random&color=fff&size=128",
                'social_link': '#'
            })

    return jsonify({'active': True, 'voter_id': active.voter_id, 'voter_name': voter.name if voter else "Unknown", 'candidates': cands_json})

@main_bp.route('/api/cast_vote', methods=['POST'])
def api_cast_vote():
    data = request.get_json() or {}
    voter_id = data.get('voter_id'); candidate_id = data.get('candidate_id'); booth_number = data.get('booth_number') or 'B1'
    if not (voter_id and candidate_id): return jsonify({'status': 'error', 'message': 'voter_id and candidate_id required'}), 400
    bs = BallotStatus.query.filter_by(voter_id=voter_id, booth_number=booth_number, is_active=True).first()
    if not bs: return jsonify({'status': 'error', 'message': 'Ballot not active'}), 403
    try:
        last_vote = Vote.query.order_by(Vote.id.desc()).first()
        prev_hash = last_vote.block_hash if last_vote else "0" * 64
        voter_hash_val = hashlib.sha256(voter_id.encode()).hexdigest()
        timestamp = datetime.utcnow()
        receipt = BlockchainUtils.generate_receipt(voter_id, candidate_id, timestamp)
        nonce = 0; block_hash = BlockchainUtils.calculate_hash("PENDING", prev_hash, candidate_id, timestamp, nonce)
        vote = Vote(voter_hash=voter_hash_val, candidate_id=candidate_id, booth_number=booth_number, receipt=receipt, timestamp=timestamp, previous_hash=prev_hash, block_hash=block_hash, nonce=nonce)
        db.session.add(vote); bs.is_active = False; db.session.commit()
    except Exception as e:
        db.session.rollback(); return jsonify({'status': 'error', 'message': str(e)}), 500
    return jsonify({'status': 'ok', 'message': 'Vote recorded on Blockchain', 'receipt': receipt})

@main_bp.route('/receipt_viewer/<booth_number>')
def receipt_page(booth_number): return render_template('receipt.html', booth_number=booth_number)

@main_bp.route('/api/poll_receipt/<booth_number>')
def api_poll_receipt(booth_number):
    vote = Vote.query.filter_by(booth_number=booth_number).order_by(Vote.timestamp.desc()).first()
    if not vote: return jsonify({'has': False})
    cand = Candidate.query.filter_by(candidate_id=vote.candidate_id).first()
    return jsonify({'has': True, 'receipt': vote.receipt, 'voter_id': "ANONYMOUS", 'candidate_name': cand.name if cand else vote.candidate_id, 'timestamp': vote.timestamp.isoformat()})

@main_bp.route('/api/verify_chain')
def api_verify_chain():
    votes = Vote.query.order_by(Vote.id.asc()).all()
    valid, msg = BlockchainUtils.verify_chain(votes)
    return jsonify({"chain_length": len(votes), "is_valid": valid, "message": msg, "last_block_hash": votes[-1].block_hash if votes else "None"})

@main_bp.route('/admin_dashboard')
def admin_dashboard():
    if session.get('role') not in ['admin', 'eci']: return redirect(url_for('main.login'))
    return render_template('admin_dashboard.html')

@main_bp.route('/booth_dashboard')
def booth_dashboard():
    if session.get('role') not in ['booth', 'eci']: return redirect(url_for('main.login'))
    return render_template('booth_dashboard.html')

@main_bp.route('/api/activity_feed')
def api_activity_feed():
    votes = Vote.query.order_by(Vote.timestamp.desc()).limit(10).all()
    activity = []
    for v in votes: activity.append({'type': 'vote', 'desc': f"New Vote Mined! (Hash: {v.block_hash[:8]}...)", 'time': v.timestamp.isoformat()})
    return jsonify(activity)

@main_bp.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(ensure_upload_folder(), filename)