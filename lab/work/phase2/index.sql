CREATE INDEX idx_email ON users(email);
SET profiling = 1;
SELECT * FROM users WHERE email = 'user777777@example.com';
SHOW PROFILES;
EXPLAIN SELECT * FROM users WHERE email = 'user777777@example.com';
