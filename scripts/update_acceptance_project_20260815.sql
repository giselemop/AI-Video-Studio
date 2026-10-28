SET NAMES utf8mb4;
START TRANSACTION;
UPDATE episodes
SET master_path = 'C:/install/AI/Data/QA/acceptance_story_20260815/MASTER_Midnight_Signal_MotionAcceptance_60s.mp4',
    subtitle_path = 'C:/install/AI/Data/QA/acceptance_story_20260815/episode-29-dialogue.srt',
    total_duration_seconds = 60.094,
    qa_status = 'Conditional',
    qa_result = JSON_OBJECT('technicalMaster', 'Passed', 'durationSeconds', 60.094, 'actionSemantic', 'BlockedOrUnverified', 'manualReviewRequired', true),
    qa_version = 1
WHERE id = 29;
UPDATE shots
SET video_path = CONCAT('C:/install/AI/Data/QA/acceptance_story_20260815/shots/shot-', LPAD(shot_number, 2, '0'), '.mp4'),
    final_video_path = CONCAT('C:/install/AI/Data/QA/acceptance_story_20260815/shots/shot-', LPAD(shot_number, 2, '0'), '.mp4'),
    qa_status = 'ManualReviewRequired',
    qa_result = JSON_OBJECT('technicalVideo', 'Passed', 'actionSemantic', CASE WHEN shot_number BETWEEN 4 AND 7 THEN 'BlockedOrUnverified' ELSE 'Unverified' END, 'identity', 'ManualReviewRequired', 'sourceReuse', true),
    qa_version = 1
WHERE episode_id = 29;
COMMIT;
SELECT id, project_id, episode_number, master_path, subtitle_path, total_duration_seconds, qa_status FROM episodes WHERE id = 29;
SELECT COUNT(*) AS shot_count, MIN(video_path), MAX(video_path), MIN(qa_status), MAX(qa_status) FROM shots WHERE episode_id = 29;
