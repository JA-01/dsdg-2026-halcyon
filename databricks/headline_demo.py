# Databricks notebook source
# MAGIC %md
# MAGIC Optional AI Functions demonstration, adapted from the organizer tour.
# MAGIC Run this notebook manually after the submission job has ingested news.
# MAGIC It only displays five headlines, changes no tables, and never feeds the
# MAGIC forecasting/scoring path. Workspace AI Functions access is required.

# COMMAND ----------
# MAGIC %sql
# MAGIC SELECT headline,
# MAGIC        ai_classify(headline, ARRAY('tariff', 'export restriction',
# MAGIC                    'shipping disruption', 'resource shortage', 'routine news')) AS topic
# MAGIC FROM (SELECT headline FROM workspace.halcyon.c2_news ORDER BY week DESC, article_id LIMIT 5)
