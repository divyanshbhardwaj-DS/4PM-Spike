import datetime
from sqlalchemy.orm import Session
from app.auth import hash_password
from app.models import (
    User, Building, Meter, MeterBoundary, MeterReading, SolarReading,
    BuildingAssignment, Dataset, DatasetVersion, DatasetImport,
    InvestigationTask, ElectricianFeedback, ManagementReview, AuditEvent
)
from app.engines.dss_engine import run_dss_deterministic_pipeline
from app.models import DSSDecision, DecisionExplanation, Recommendation, DataQualityFinding

def seed_database(db: Session):
    """
    Seeds initial realistic campus dataset for Case 05: The 4 PM Spike.
    All data is realistic and grounded in university electrical distribution engineering.
    """
    # 1. Seed Users if not present
    if db.query(User).count() == 0:
        elec1 = User(
            username="electrician1",
            email="electrician1@campus.edu",
            full_name="Marcus Vance, Master Electrician",
            role="ELECTRICIAN",
            hashed_password=hash_password("sparky2026!"),
            is_active=True
        )
        elec2 = User(
            username="electrician2",
            email="electrician2@campus.edu",
            full_name="Elena Rostova, High Voltage Specialist",
            role="ELECTRICIAN",
            hashed_password=hash_password("current2026!"),
            is_active=True
        )
        mgr = User(
            username="manager1",
            email="manager1@campus.edu",
            full_name="Dr. Sarah Chen, Director of Campus Energy Operations",
            role="MANAGEMENT",
            hashed_password=hash_password("director2026!"),
            is_active=True
        )
        admin = User(
            username="admin1",
            email="admin1@campus.edu",
            full_name="James Thorne, Campus Infrastructure Admin",
            role="ADMIN",
            hashed_password=hash_password("admin2026!"),
            is_active=True
        )
        db.add_all([elec1, elec2, mgr, admin])
        db.commit()

    elec1 = db.query(User).filter(User.username == "electrician1").first()
    elec2 = db.query(User).filter(User.username == "electrician2").first()
    mgr = db.query(User).filter(User.username == "manager1").first()

    # 2. Seed Dataset & Version
    if db.query(Dataset).count() == 0:
        dataset = Dataset(
            name="University Substation Energy Telemetry 2026",
            description="Core 15-minute campus electrical distribution loggers covering the 16:00-20:00 demand window."
        )
        db.add(dataset)
        db.commit()

        dataset_version = DatasetVersion(
            dataset_id=dataset.id,
            version_num=1,
            source="Campus Central SCADA Substation Feed",
            file_format="CSV",
            record_count=0,
            date_range_start=datetime.datetime(2026, 10, 27, 0, 0),
            date_range_end=datetime.datetime(2026, 10, 29, 23, 45),
            columns_json=["timestamp", "building_code", "meter_code", "power_kw", "energy_kwh", "solar_kw"],
            units="kW, kWh",
            provenance_type="CAMPUS_MEASURED",
            validation_summary={"status": "INITIALIZED"}
        )
        db.add(dataset_version)
        db.commit()
    else:
        dataset_version = db.query(DatasetVersion).first()

    # 3. Seed Buildings
    if db.query(Building).count() == 0:
        b1 = Building(
            name="Engineering Research Complex",
            code="BLD-ENG",
            category="LAB",
            is_protected=False,
            safety_notes="Standard industrial research labs. Heavy wind tunnel and CNC machinery."
        )
        b2 = Building(
            name="Supercomputing & Data Center",
            code="BLD-DC",
            category="RESEARCH",
            is_protected=True,
            safety_notes="Mission-critical supercomputing clusters and liquid cooling infrastructure. Strict non-sheddable power envelope."
        )
        b3 = Building(
            name="Science & Chemistry Labs",
            code="BLD-SCI",
            category="LAB",
            is_protected=True,
            safety_notes="BSL-3 containment exhaust scrubbers and active volatile chemical storage ventilation."
        )
        b4 = Building(
            name="Main Student Union",
            code="BLD-SU",
            category="ACADEMIC",
            is_protected=False,
            safety_notes="Dining halls, retail, auditorium. 120 kW rooftop solar PV system."
        )
        b5 = Building(
            name="Humanities & Arts Hall",
            code="BLD-HUM",
            category="ACADEMIC",
            is_protected=False,
            safety_notes="Lecture theatres, faculty offices, fine arts studio."
        )
        b6 = Building(
            name="Central Library",
            code="BLD-LIB",
            category="ACADEMIC",
            is_protected=False,
            safety_notes="Multi-story study facility with high evening HVAC and lighting draw."
        )
        b7 = Building(
            name="Athletics & Recreation Center",
            code="BLD-ATH",
            category="RECREATION",
            is_protected=False,
            safety_notes="Indoor pool, gymnasium, high-output LED arena lighting."
        )
        b8 = Building(
            name="North Campus Dormitory A",
            code="BLD-DORM",
            category="RESIDENTIAL",
            is_protected=False,
            safety_notes="Student residence housing 450 undergraduates."
        )
        db.add_all([b1, b2, b3, b4, b5, b6, b7, b8])
        db.commit()

        # Seed Meters
        meters = [
            Meter(meter_code="MTR-ENG-01", building_id=b1.id, boundary_type="GROSS", register_type="MAIN_FEED", unit="kW", status="ACTIVE"),
            Meter(meter_code="MTR-DC-01", building_id=b2.id, boundary_type="GROSS", register_type="MAIN_FEED", unit="kW", status="ACTIVE"),
            Meter(meter_code="MTR-SCI-01", building_id=b3.id, boundary_type="GROSS", register_type="MAIN_FEED", unit="kW", status="ACTIVE"),
            Meter(meter_code="MTR-SU-01", building_id=b4.id, boundary_type="GROSS", register_type="MAIN_FEED", unit="kW", status="ACTIVE"),
            Meter(meter_code="MTR-HUM-01", building_id=b5.id, boundary_type="UNDECLARED", register_type="MAIN_FEED", unit="kW", status="ACTIVE"),
            Meter(meter_code="MTR-LIB-01", building_id=b6.id, boundary_type="GROSS", register_type="MAIN_FEED", unit="kW", status="ACTIVE"),
            Meter(meter_code="MTR-ATH-01", building_id=b7.id, boundary_type="GROSS", register_type="MAIN_FEED", unit="kW", status="ACTIVE"),
            Meter(meter_code="MTR-DORM-01", building_id=b8.id, boundary_type="GROSS", register_type="MAIN_FEED", unit="kW", status="ACTIVE"),
        ]
        db.add_all(meters)
        db.commit()

        # Seed Building Assignments
        assignments = [
            BuildingAssignment(user_id=elec1.id, building_id=b1.id),
            BuildingAssignment(user_id=elec1.id, building_id=b5.id),
            BuildingAssignment(user_id=elec1.id, building_id=b8.id),
            BuildingAssignment(user_id=elec2.id, building_id=b3.id),
            BuildingAssignment(user_id=elec2.id, building_id=b6.id),
            BuildingAssignment(user_id=elec2.id, building_id=b7.id),
        ]
        db.add_all(assignments)
        db.commit()

        # 4. Generate 15-Minute Interval Telemetry
        # Dates: 2026-10-28 and 2026-10-29
        target_dates = [datetime.date(2026, 10, 28), datetime.date(2026, 10, 29)]
        all_readings = []
        solar_readings = []

        for d in target_dates:
            # 24 hours in 15-min intervals = 96 intervals
            for h in range(24):
                for m in [0, 15, 30, 45]:
                    dt = datetime.datetime.combine(d, datetime.time(h, m))

                    # Solar profile (peaks around noon, zero at night)
                    solar_kw = 0.0
                    if 6 <= h < 18:
                        solar_kw = max(0.0, round(120.0 * (1.0 - abs(h + m/60.0 - 12.0) / 6.0), 2))
                    solar_readings.append(SolarReading(
                        building_id=b4.id,
                        meter_id=meters[3].id,
                        timestamp=dt,
                        interval_minutes=15,
                        generation_kw=solar_kw,
                        raw_value=solar_kw,
                        is_valid=True,
                        dataset_version_id=dataset_version.id
                    ))

                    # BLD-ENG: Normal day ~350 kW, sharp 4 PM Spike at 16:30 up to 540 kW
                    eng_base = 350.0 + (h * 5.0)
                    if 16 <= h < 20:
                        eng_base += 150.0 + ((m % 30) * 2.0)
                    all_readings.append(MeterReading(
                        meter_id=meters[0].id, timestamp=dt, interval_minutes=15,
                        power_kw=round(eng_base, 2), energy_kwh=round(eng_base * 0.25, 2),
                        raw_value=round(eng_base, 2), is_valid=True, dataset_version_id=dataset_version.id
                    ))

                    # BLD-DC: Supercomputer steady baseline ~630 kW (Protected)
                    dc_val = 620.0 + (h % 3) * 10.0 + (m % 15)
                    all_readings.append(MeterReading(
                        meter_id=meters[1].id, timestamp=dt, interval_minutes=15,
                        power_kw=round(dc_val, 2), energy_kwh=round(dc_val * 0.25, 2),
                        raw_value=round(dc_val, 2), is_valid=True, dataset_version_id=dataset_version.id
                    ))

                    # BLD-SCI: Science labs peak ~490 kW at 17:00 (Protected)
                    sci_val = 300.0 + (180.0 if (16 <= h < 19) else 20.0) + (m % 20)
                    all_readings.append(MeterReading(
                        meter_id=meters[2].id, timestamp=dt, interval_minutes=15,
                        power_kw=round(sci_val, 2), energy_kwh=round(sci_val * 0.25, 2),
                        raw_value=round(sci_val, 2), is_valid=True, dataset_version_id=dataset_version.id
                    ))

                    # BLD-SU: Student Union gross ~320 kW (has solar)
                    su_val = 220.0 + (100.0 if (11 <= h < 20) else 10.0)
                    all_readings.append(MeterReading(
                        meter_id=meters[3].id, timestamp=dt, interval_minutes=15,
                        power_kw=round(su_val, 2), energy_kwh=round(su_val * 0.25, 2),
                        raw_value=round(su_val, 2), is_valid=True, dataset_version_id=dataset_version.id
                    ))

                    # BLD-HUM: Humanities ~210 kW (UNDECLARED boundary)
                    hum_val = 180.0 + (30.0 if (9 <= h < 18) else 0.0)
                    all_readings.append(MeterReading(
                        meter_id=meters[4].id, timestamp=dt, interval_minutes=15,
                        power_kw=round(hum_val, 2), energy_kwh=round(hum_val * 0.25, 2),
                        raw_value=round(hum_val, 2), is_valid=True, dataset_version_id=dataset_version.id
                    ))

                    # BLD-LIB: Library ~340 kW (Needs submetering for chiller vs lighting)
                    lib_val = 200.0 + (140.0 if (14 <= h < 22) else 20.0)
                    all_readings.append(MeterReading(
                        meter_id=meters[5].id, timestamp=dt, interval_minutes=15,
                        power_kw=round(lib_val, 2), energy_kwh=round(lib_val * 0.25, 2),
                        raw_value=round(lib_val, 2), is_valid=True, dataset_version_id=dataset_version.id
                    ))

                    # BLD-ATH: Missing intervals between 17:00 and 18:30 on 2026-10-29 (<90% complete!)
                    if d == datetime.date(2026, 10, 29) and 17 <= h < 19:
                        # Omit reading - never zero-fill!
                        pass
                    else:
                        ath_val = 240.0 + (80.0 if (16 <= h < 21) else 10.0)
                        all_readings.append(MeterReading(
                            meter_id=meters[6].id, timestamp=dt, interval_minutes=15,
                            power_kw=round(ath_val, 2), energy_kwh=round(ath_val * 0.25, 2),
                            raw_value=round(ath_val, 2), is_valid=True, dataset_version_id=dataset_version.id
                        ))

                    # BLD-DORM: Negative spike anomaly at 16:45 on 2026-10-29 (-65.0 kW) -> AUDIT_REGISTER
                    if d == datetime.date(2026, 10, 29) and h == 16 and m == 45:
                        dorm_val = -65.0
                        all_readings.append(MeterReading(
                            meter_id=meters[7].id, timestamp=dt, interval_minutes=15,
                            power_kw=dorm_val, energy_kwh=None, raw_value=dorm_val,
                            is_valid=False, validation_flags="NEGATIVE_ON_GROSS",
                            dataset_version_id=dataset_version.id
                        ))
                    else:
                        dorm_val = 150.0 + (110.0 if (17 <= h < 23) else 20.0)
                        all_readings.append(MeterReading(
                            meter_id=meters[7].id, timestamp=dt, interval_minutes=15,
                            power_kw=round(dorm_val, 2), energy_kwh=round(dorm_val * 0.25, 2),
                            raw_value=round(dorm_val, 2), is_valid=True, dataset_version_id=dataset_version.id
                        ))

        db.add_all(solar_readings)
        db.add_all(all_readings)
        db.commit()

        dataset_version.record_count = len(all_readings) + len(solar_readings)
        db.commit()

        # 5. Run Initial Deterministic DSS Pipeline for all Buildings
        for b, m in zip([b1, b2, b3, b4, b5, b6, b7, b8], meters):
            b_readings = [
                {"timestamp": r.timestamp, "power_kw": r.power_kw, "energy_kwh": r.energy_kwh, "is_valid": r.is_valid}
                for r in all_readings if r.meter_id == m.id
            ]
            s_readings = [
                {"timestamp": s.timestamp, "generation_kw": s.generation_kw, "is_valid": s.is_valid}
                for s in solar_readings if s.building_id == b.id
            ]

            baseline = 380.0 if b.code == "BLD-ENG" else (600.0 if b.code == "BLD-DC" else (320.0 if b.code == "BLD-SCI" else 200.0))

            res = run_dss_deterministic_pipeline(
                building_dict={"name": b.name, "code": b.code, "is_protected": b.is_protected},
                meter_dict={"meter_code": m.meter_code, "boundary_type": m.boundary_type, "status": m.status, "register_type": m.register_type},
                readings=b_readings,
                solar_readings=s_readings,
                target_dates=target_dates,
                historical_baseline_kw=baseline,
                has_physical_inspection_on_record=(b.code == "BLD-DC"), # Data Center has certified inspection
                has_calibration_cert_on_record=(b.code == "BLD-DC")
            )

            # Persist Decision
            decision = DSSDecision(
                decision_code=res["decision_code"],
                building_id=b.id,
                meter_id=m.id,
                dataset_version_id=dataset_version.id,
                rule_version=res["rule_version"],
                evidence_grade=res["evidence_grade"],
                severity=res["severity"],
                eligibility=res["eligibility"],
                recommended_action=res["recommended_action"],
                human_review_required=res["human_review_required"],
                status="PENDING_REVIEW"
            )
            db.add(decision)
            db.commit()

            # Persist Explanation
            exp_data = res["explanation"]
            explanation = DecisionExplanation(
                decision_id=decision.id,
                what_decided=exp_data["what_decided"],
                why_decided=exp_data["why_decided"],
                data_used_json=exp_data["data_used_json"],
                rule_applied=exp_data["rule_applied"],
                calculation_details=exp_data["calculation_details"],
                supporting_evidence_json=exp_data["supporting_evidence_json"],
                missing_information=exp_data["missing_information"],
                uncertainty=exp_data["uncertainty"],
                what_could_change=exp_data["what_could_change"],
                recommended_next_step=exp_data["recommended_next_step"],
                responsible_role=exp_data["responsible_role"],
                source_provenance=exp_data["source_provenance"]
            )
            db.add(explanation)

            # Persist Recommendation
            recommendation = Recommendation(
                decision_id=decision.id,
                title=f"Advisory Action: {res['decision_code']} for {b.name}",
                description=res["recommended_action"],
                urgency=res["severity"],
                action_type=res["decision_code"],
                status="PENDING_REVIEW"
            )
            db.add(recommendation)

            # Persist Data Quality Findings
            for f in res.get("data_quality_findings", []):
                dqf = DataQualityFinding(
                    dataset_version_id=dataset_version.id,
                    building_id=b.id,
                    meter_id=m.id,
                    issue_category=f["issue_category"],
                    severity=f["severity"],
                    validation_rule=f["validation_rule"],
                    explanation=f["explanation"],
                    recommended_action=f["recommended_action"],
                    status=f["status"]
                )
                db.add(dqf)

            db.commit()

        # Seed initial sample investigation tasks
        b_dorm = db.query(Building).filter(Building.code == "BLD-DORM").first()
        m_dorm = db.query(Meter).filter(Meter.building_id == b_dorm.id).first()
        dec_dorm = db.query(DSSDecision).filter(DSSDecision.building_id == b_dorm.id).first()

        task1 = InvestigationTask(
            building_id=b_dorm.id,
            meter_id=m_dorm.id,
            decision_id=dec_dorm.id if dec_dorm else None,
            assigned_to_user_id=elec1.id,
            assigned_by_user_id=mgr.id,
            priority="CRITICAL",
            status="ASSIGNED",
            required_inspection="Physical inspection of Current Transformer (CT) polarity and Register 2 wiring to resolve negative demand spike (-65 kW).",
            instructions="Check junction box JB-204 in basement electrical switchgear room. Test with calibrated digital multimeter.",
            due_date=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
        )

        b_hum = db.query(Building).filter(Building.code == "BLD-HUM").first()
        m_hum = db.query(Meter).filter(Meter.building_id == b_hum.id).first()
        dec_hum = db.query(DSSDecision).filter(DSSDecision.building_id == b_hum.id).first()

        task2 = InvestigationTask(
            building_id=b_hum.id,
            meter_id=m_hum.id,
            decision_id=dec_hum.id if dec_hum else None,
            assigned_to_user_id=elec1.id,
            assigned_by_user_id=mgr.id,
            priority="HIGH",
            status="IN_PROGRESS",
            required_inspection="Verify whether meter MTR-HUM-01 feeds gross building service or net utility interconnect.",
            instructions="Review electrical single-line diagram SLD-HUM-04 and inspect physical meter nameplate.",
            due_date=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=2)
        )

        db.add_all([task1, task2])
        db.commit()

        # Initial Audit Event
        audit = AuditEvent(
            user_id=admin.id,
            role="ADMIN",
            event_type="SYSTEM_INITIALIZATION",
            entity_type="SYSTEM",
            entity_id="DSS-1.0",
            action_details={"message": "DSS-1.0 system initialized with Case 05: The 4 PM Spike seed dataset."},
            ip_address="127.0.0.1",
            is_immutable=True
        )
        db.add(audit)
        db.commit()

