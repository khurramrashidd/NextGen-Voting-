from flask import Flask, session
from config import Config
from models import db, Voter, Admin
import random
from datetime import datetime, timedelta

from routes import main_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    db.init_app(app)
    app.register_blueprint(main_bp)
    
    with app.app_context():
        db.create_all()

        # Seed Admin
        if not Admin.query.filter_by(username='admin').first():
            admin = Admin(username='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("✅ Admin created (admin/admin123)")

        # Seed 60 Dummy Voters
        if Voter.query.count() < 10:
            print("🌱 Seeding 60 Dummy Voters...")
            states = ["Maharashtra", "Delhi", "UP", "Karnataka", "Bihar"]
            assemblies = ["Panvel", "Hajipur", "Chandni Chowk", "Bangalore South", "Patna"]
            
            for i in range(1, 61):
                vid = f"VOT{10000+i}"
                aadhaar = f"9999{10000000+i}"
                state = random.choice(states)
                
                v = Voter(
                    voter_id=vid,
                    aadhaar=aadhaar,
                    name=f"Voter {i}",
                    dob=datetime(1980 + (i%20), 1, 1).date(),
                    father_name=f"Father of Voter {i}",
                    gender="Male" if i % 2 == 0 else "Female",
                    address=f"House No {i}, Sector {i%10}, {state}",
                    assembly=random.choice(assemblies),
                    part_no=f"Part-{i%5 + 1}",
                    serial_no=f"SL-{i}",
                    face_image=None # Placeholder
                )
                db.session.add(v)
            try:
                db.session.commit()
                print("✅ 60 Dummy Voters created")
            except Exception as e:
                db.session.rollback()
                print(f"⚠️ Seeding error: {e}")

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(port = 5000, host = "0.0.0.0", debug=True)