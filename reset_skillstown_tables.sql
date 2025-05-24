-- SkillsTown Database Reset SQL Script
-- This script drops and recreates SkillsTown tables with correct foreign key constraints

-- Drop existing SkillsTown tables (preserve user table)
DROP TABLE IF EXISTS skillstown_user_courses CASCADE;
DROP TABLE IF EXISTS skillstown_user_profiles CASCADE;
DROP TABLE IF EXISTS skillstown_courses CASCADE;

-- Recreate SkillsTown tables with correct foreign key references

-- SkillsTown Courses table
CREATE TABLE skillstown_courses (
    id SERIAL PRIMARY KEY,
    category VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    url VARCHAR(500),
    provider VARCHAR(100) DEFAULT 'SkillsTown',
    skills_taught TEXT,
    difficulty_level VARCHAR(20),
    duration VARCHAR(50),
    keywords TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- User Courses table (with correct foreign key to 'user' table)
CREATE TABLE skillstown_user_courses (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    category VARCHAR(100) NOT NULL,
    course_name VARCHAR(255) NOT NULL,
    status VARCHAR(50) DEFAULT 'enrolled',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT skillstown_user_course_unique UNIQUE (user_id, course_name)
);

-- User Profiles table (with correct foreign key to 'user' table)
CREATE TABLE skillstown_user_profiles (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    cv_text TEXT,
    skills TEXT,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Verify the foreign key constraints
SELECT 
    tc.constraint_name, 
    tc.table_name, 
    kcu.column_name, 
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name 
FROM 
    information_schema.table_constraints AS tc 
    JOIN information_schema.key_column_usage AS kcu
      ON tc.constraint_name = kcu.constraint_name
    JOIN information_schema.constraint_column_usage AS ccu
      ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY' 
AND tc.table_name LIKE 'skillstown_%';
