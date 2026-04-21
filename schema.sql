CREATE OR REPLACE TABLE `ai-statistics-493215.claude_ai_usage.daily_tokens`
(
  start_time                  TIMESTAMP NOT NULL,
  end_time                    TIMESTAMP NOT NULL,
  model                       STRING,
  workspace_id                STRING,
  input_tokens                INT64,
  output_tokens               INT64,
  cache_read_input_tokens     INT64,
  cache_creation_input_tokens INT64
)
PARTITION BY DATE(start_time)
OPTIONS (require_partition_filter = FALSE);

CREATE OR REPLACE TABLE `ai-statistics-493215.claude_ai_usage.user_daily_tokens`
(
  start_time                  TIMESTAMP NOT NULL,
  end_time                    TIMESTAMP NOT NULL,
  model                       STRING,
  workspace_id                STRING,
  user                        STRING,
  input_tokens                INT64,
  output_tokens               INT64,
  cache_read_input_tokens     INT64,
  cache_creation_input_tokens INT64
)
PARTITION BY DATE(start_time)
OPTIONS (require_partition_filter = FALSE);
