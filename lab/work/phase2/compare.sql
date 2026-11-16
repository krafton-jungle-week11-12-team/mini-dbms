SET profiling = 1;
SELECT * FROM users WHERE id = 777777;
SELECT * FROM users WHERE email = 'user777777@example.com';
SHOW PROFILES;
EXPLAIN SELECT * FROM users WHERE id = 777777;
EXPLAIN SELECT * FROM users WHERE email = 'user777777@example.com';
EXPLAIN ANALYZE SELECT * FROM users WHERE email = 'user777777@example.com';
