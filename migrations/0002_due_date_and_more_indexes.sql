-- Adiciona due_date às tarefas e alguns índices extras

PRAGMA foreign_keys = ON;

ALTER TABLE assignments ADD COLUMN due_date DATETIME;

CREATE INDEX IF NOT EXISTS idx_submissions_assignment ON submissions(assignment_id);
CREATE INDEX IF NOT EXISTS idx_course_instr_user      ON course_instructors(user_id);