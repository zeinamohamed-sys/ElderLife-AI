CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    age INT,
    emergency_contact VARCHAR(20)
);

CREATE TABLE sensor_logs (
    log_id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(user_id),
    timestamp TIMESTAMP,
    activity_type VARCHAR(50),
    sensor_value VARCHAR(100)
);

CREATE TABLE fall_alerts (
    alert_id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(user_id),
    detected_time TIMESTAMP,
    confidence_score FLOAT,
    status VARCHAR(20)
);

CREATE TABLE care_plans (
    reminder_id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(user_id),
    task_type VARCHAR(50),
    scheduled_time TIMESTAMP,
    is_completed BOOLEAN
);

CREATE TABLE check_ins (
    checkin_id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(user_id),
    expected_time TIMESTAMP,
    actual_time TIMESTAMP,
    status VARCHAR(20)
);
