# Databricks notebook source
# DBTITLE 1,Passed variables
dbutils.widgets.text("min_dbr_version", "12.0", "Min required DBR version")

#Empty value will try default: ?? with a fallback to hive_metastore
#Specifying a value will not have fallback and fail if the catalog can't be used/created
dbutils.widgets.text("catalog", "", "Catalog")

#ignored if db is set (we force the databse to the given value in this case)
dbutils.widgets.text("project_name", "", "Project Name")

#Empty value will be set to a database scoped to the current user using project_name
dbutils.widgets.text("db", "", "Database")

dbutils.widgets.text("data_path", "", "Data Path")

# COMMAND ----------

# DBTITLE 1,Running checks
from pyspark.sql.types import *
import re

# REQUIRES A PROJECT NAME -------------------------
project_name = dbutils.widgets.get('project_name')
assert len(project_name) > 0, "project_name is a required variable"


# VERIFY DATABRICKS VERSION COMPATIBILITY ----------
try:
  min_required_version = dbutils.widgets.get("min_dbr_version")
except:
  min_required_version = "13.0"

version_tag = spark.conf.get("spark.databricks.clusterUsageTags.sparkVersion")
version_search = re.search('^([0-9]*\.[0-9]*)', version_tag)
assert version_search, f"The Databricks version can't be extracted from {version_tag}, shouldn't happen, please correct the regex"
current_version = float(version_search.group(1))
assert float(current_version) >= float(min_required_version), f'The Databricks version of the cluster must be >= {min_required_version}. Current version detected: {current_version}'
assert "ml" in version_tag.lower(), f"The Databricks ML runtime must be used. Current version detected doesn't contain 'ml': {version_tag} "

# COMMAND ----------

# DBTITLE 1,Catalog and database setup
# DATABASE SETUP -----------------------------------
current_user = dbutils.notebook.entry_point.getDbutils().notebook().getContext().tags().apply('user')
if current_user.rfind('@') > 0:
  current_user_no_at = current_user[:current_user.rfind('@')]
else:
  current_user_no_at = current_user
current_user_no_at = re.sub(r'\W+', '_', current_user_no_at)

#Try to use the UC catalog when possible. If not will fallback to hive_metastore
catalog = dbutils.widgets.get("catalog")
db = dbutils.widgets.get("db")
if len(catalog) == 0:
  dbName = "lakehouse_in_action"
elif len(db)==0:
  dbName = project_name
else:
  dbName = db
  
data_path = dbutils.widgets.get('data_path')
if len(data_path) == 0:
  cloud_storage_path = f"/Users/{current_user}/lakehouse_in_action/{project_name}"
else:
  cloud_storage_path = data_path

def use_and_create_db(catalog, dbName, cloud_storage_path = None):
  print(f"USE CATALOG `{catalog}`")
  spark.sql(f"USE CATALOG `{catalog}`")
  if cloud_storage_path == None or catalog not in ['hive_metastore', 'spark_catalog']:
    spark.sql(f"""create database if not exists `{dbName}` """)
  else:
    spark.sql(f"""create database if not exists `{dbName}` LOCATION '{cloud_storage_path}/tables' """)

if catalog == "spark_catalog":
  catalog = "hive_metastore"
  
#If the catalog is defined, we force it to the given value and throw exception if not.
if len(catalog) > 0:
  current_catalog = spark.sql("select current_catalog()").collect()[0]['current_catalog()']
  if current_catalog != catalog:
    catalogs = [r['catalog'] for r in spark.sql("SHOW CATALOGS").collect()]
    if catalog not in catalogs and catalog not in ['hive_metastore', 'spark_catalog']:
      spark.sql(f"CREATE CATALOG IF NOT EXISTS {catalog}")
  use_and_create_db(catalog, dbName)
else:
  #otherwise we'll try to setup the catalog to lakehouse_in_action and create the database here. If we can't we'll fallback to legacy hive_metastore
  print("Try to setup UC catalog")
  try:
    catalogs = [r['catalog'] for r in spark.sql("SHOW CATALOGS").collect()]
    if len(catalogs) == 1 and catalogs[0] in ['hive_metastore', 'spark_catalog']:
      print(f"UC doesn't appear to be enabled, will fallback to hive_metastore (spark_catalog)")
      catalog = "hive_metastore"
    else:
      if "lakehouse_in_action" not in catalogs:
        spark.sql("CREATE CATALOG IF NOT EXISTS lakehouse_in_action")
      catalog = "lakehouse_in_action"
    use_and_create_db(catalog, dbName)
  except Exception as e:
    print(f"error with catalog {e}, do you have permission or UC enabled? will fallback to hive_metastore")
    catalog = "hive_metastore"
    use_and_create_db(catalog, dbName)

print(f"using cloud_storage_path {cloud_storage_path}")
print(f"using catalog.database `{catalog}`.`{dbName}`")

#Add the catalog to cloud storage path as we could have 1 checkpoint location different per catalog
if catalog not in ['hive_metastore', 'spark_catalog']:
  cloud_storage_path+="_"+catalog
  try:
    spark.sql(f"GRANT CREATE, USAGE on DATABASE {catalog}.{dbName} TO `account users`")
    spark.sql(f"ALTER SCHEMA {catalog}.{dbName} OWNER TO `account users`")
  except Exception as e:
    print("Couldn't grant access to the schema to all users:"+str(e))
  
#with parallel execution this can fail the time of the initialization. add a few retry to fix these issues
for i in range(10):
  try:
    spark.sql(f"""USE `{catalog}`.`{dbName}`""")
    break
  except Exception as e:
    time.sleep(1)
    if i >= 9:
      raise e

# COMMAND ----------

# DBTITLE 1,Get Kaggle credentials using secrets
# import os
# # os.environ['kaggle_username'] = 'YOUR KAGGLE USERNAME HERE' # replace with your own credential here temporarily or set up a secret scope with your credential
# os.environ['kaggle_username'] = dbutils.secrets.get("lakehouse-in-action", "kaggle_username")

# # os.environ['kaggle_key'] = 'YOUR KAGGLE KEY HERE' # replace with your own credential here temporarily or set up a secret scope with your credential
# os.environ['kaggle_key'] = dbutils.secrets.get("lakehouse-in-action", "kaggle_key")
