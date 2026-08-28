-- 书桌学习伴侣 · 数据层
-- TiDB Cloud Serverless (MySQL 8.0 兼容)。行存走 TiKV，报表与向量检索自动下推 TiFlash。

CREATE TABLE IF NOT EXISTS child (
  child_id     VARCHAR(64)  PRIMARY KEY,
  display_name VARCHAR(64)  NOT NULL,
  grade        VARCHAR(32),
  created_at   DATETIME     DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS device (
  device_id    VARCHAR(64)  PRIMARY KEY,
  child_id     VARCHAR(64)  NOT NULL,
  name         VARCHAR(64),
  firmware     VARCHAR(32),
  last_seen    DATETIME,
  KEY idx_child (child_id)
);

-- 60 秒聚合。10 秒原始数据留在设备 SD 卡，云端不存 —— 行数降到 1/6，
-- 家长端时间轴用 60 秒粒度完全够。
CREATE TABLE IF NOT EXISTS sensor_minute (
  id            BIGINT AUTO_INCREMENT PRIMARY KEY,
  child_id      VARCHAR(64) NOT NULL,
  device_id     VARCHAR(64) NOT NULL,
  ts            DATETIME    NOT NULL,
  present       TINYINT     NOT NULL DEFAULT 0,
  distance_mm   INT,
  light_left    INT,
  light_right   INT,
  temperature   DECIMAL(4,1),
  humidity      TINYINT,
  pir_hits      SMALLINT    DEFAULT 0,
  abnormal      TINYINT     DEFAULT 0,
  UNIQUE KEY uq_ts (child_id, ts),
  KEY idx_child_ts (child_id, ts)
);

CREATE TABLE IF NOT EXISTS study_session (
  session_id     VARCHAR(64) PRIMARY KEY,
  child_id       VARCHAR(64) NOT NULL,
  started_at     DATETIME    NOT NULL,
  ended_at       DATETIME,
  duration_s     INT         DEFAULT 0,
  present_ratio  DECIMAL(4,3),
  avg_distance   INT,
  close_events   INT DEFAULT 0,
  close_seconds  INT DEFAULT 0,
  lowlight_secs  INT DEFAULT 0,
  interruptions  INT DEFAULT 0,
  eye_score      TINYINT,
  -- 16 维手工特征向量。不用文本 embedding：零模型成本、低维、每维可解释。
  -- 距离函数用 L2 而非 cosine —— 余弦忽略模长，但这里模长就是信号本身。
  embedding      VECTOR(16),
  KEY idx_child_time (child_id, started_at),
  VECTOR INDEX idx_emb ((VEC_L2_DISTANCE(embedding)))
);

CREATE TABLE IF NOT EXISTS reminder_event (
  id           BIGINT AUTO_INCREMENT PRIMARY KEY,
  child_id     VARCHAR(64) NOT NULL,
  fired_at     DATETIME    NOT NULL,
  kind         VARCHAR(32) NOT NULL,       -- 台灯偏暗 / 距离偏近 / 休息喝水
  -- 响应结果：提醒后观察窗口内该项指标有没有回到区间。
  -- 这是本产品独有的指标，别的产品只能报「提醒了几次」。
  improved     TINYINT,                    -- NULL = 还在观察窗口内
  detail       VARCHAR(255),
  resolved_s   INT,
  KEY idx_child_time (child_id, fired_at)
);

CREATE TABLE IF NOT EXISTS pet_state (
  child_id   VARCHAR(64) PRIMARY KEY,
  hp         TINYINT  DEFAULT 100,
  grow       INT      DEFAULT 0,
  form       VARCHAR(16) DEFAULT 'normal',
  updated_at DATETIME
);

CREATE TABLE IF NOT EXISTS device_config (
  child_id      VARCHAR(64) PRIMARY KEY,
  rev           INT DEFAULT 1,             -- 设备比对 rev，变了就落盘生效
  goal_hours    TINYINT DEFAULT 4,
  distance_min  INT DEFAULT 400,
  distance_max  INT DEFAULT 850,
  light_min     INT DEFAULT 3600,          -- 实测常态 3935，1500 几乎永不触发
  cooldown_s    INT DEFAULT 1800,
  voice_on      TINYINT DEFAULT 1,
  anim_on       TINYINT DEFAULT 1,
  push_on       TINYINT DEFAULT 1,
  child_visible TINYINT DEFAULT 1,
  updated_at    DATETIME
);

CREATE TABLE IF NOT EXISTS ask_log (
  id        BIGINT AUTO_INCREMENT PRIMARY KEY,
  child_id  VARCHAR(64) NOT NULL,
  asked_at  DATETIME    NOT NULL,
  topic     VARCHAR(64),
  question  TEXT,
  answer    TEXT,
  KEY idx_child_time (child_id, asked_at)
);
