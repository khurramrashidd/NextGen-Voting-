from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy() 

# -----------------
# Models
# -----------------

class DigiLockerDummy(db.Model):
    __tablename__ = "digilocker_dummy"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    dob = db.Column(db.String(20))
    aadhaar = db.Column(db.String(12), unique=True)
    address = db.Column(db.String(200))
    party = db.Column(db.String(100))
    constituency = db.Column(db.String(100))
    email = db.Column(db.String(100))
    phone = db.Column(db.String(15))


class Nomination(db.Model):
    __tablename__ = "nominations"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    dob = db.Column(db.String(20))
    aadhaar = db.Column(db.String(12)) # Not unique here to allow re-application logic if needed, but logic enforces 1 active
    address = db.Column(db.String(200))
    party = db.Column(db.String(100))
    constituency = db.Column(db.String(100))
    state = db.Column(db.String(100)) # Added State
    email = db.Column(db.String(100))
    phone = db.Column(db.String(15))
    
    # Docs
    affidavit = db.Column(db.String(200))
    property_cert = db.Column(db.String(200))
    education_cert = db.Column(db.String(200))
    criminal_record = db.Column(db.String(200))
    
    # Status & Auth
    status = db.Column(db.String(20), default="Pending")
    rejection_reason = db.Column(db.String(255), nullable=True) # New field
    username = db.Column(db.String(50), unique=True) # Aadhaar used as username
    password = db.Column(db.String(200))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    reviewed_by = db.Column(db.String(50), nullable=True)

class Voter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    voter_id = db.Column(db.String(64), unique=True, nullable=False)
    aadhaar = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    dob = db.Column(db.Date, nullable=False)
    face_image = db.Column(db.String(256), nullable=True)
    
    # New Details
    father_name = db.Column(db.String(100))
    gender = db.Column(db.String(20))
    address = db.Column(db.String(255))
    assembly = db.Column(db.String(100))
    part_no = db.Column(db.String(50))
    serial_no = db.Column(db.String(50))

    def __repr__(self):
        return f"<Voter {self.voter_id} - {self.name}>"

class Candidate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    party = db.Column(db.String(64), nullable=False)
    constituency = db.Column(db.String(120), nullable=False)
    state = db.Column(db.String(100), nullable=True)

    def __repr__(self):
        return f"<Candidate {self.candidate_id} - {self.name}>"

class CandidateUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    aadhaar = db.Column(db.String(12), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    voter_hash = db.Column(db.String(64), nullable=True) 
    candidate_id = db.Column(db.String(64), nullable=False)
    booth_number = db.Column(db.String(32), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    receipt = db.Column(db.String(64))
    previous_hash = db.Column(db.String(64), nullable=True)
    block_hash = db.Column(db.String(64), nullable=True)
    nonce = db.Column(db.Integer, default=0)

class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class BoothOfficer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    booth_number = db.Column(db.String(32), nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class BallotStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    voter_id = db.Column(db.String(64), nullable=False)
    booth_number = db.Column(db.String(32), nullable=False)
    is_active = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class MismatchLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    aadhaar = db.Column(db.String(20), nullable=False)
    voter_id = db.Column(db.String(64), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    note = db.Column(db.String(256))