DROP TABLE IF EXISTS users;
CREATE TABLE users (
  id    BIGINT AUTO_INCREMENT PRIMARY KEY,
  name  VARCHAR(30) NOT NULL,
  age   INT NOT NULL,
  email VARCHAR(60) NOT NULL
) ENGINE=InnoDB;

SET SESSION cte_max_recursion_depth = 1000000;
INSERT INTO users (name, age, email)
WITH RECURSIVE seq(n) AS (
  SELECT 1 UNION ALL SELECT n + 1 FROM seq WHERE n < 1000000
)
SELECT CONCAT('user', n), 20 + (n % 50), CONCAT('user', n, '@example.com') FROM seq;

SELECT COUNT(*) AS total_rows FROM users;
