# Apache Zeppelin Nexmark notebooks

The notebooks in this directory are used to initialize data in Kafka (for Streambed estimation, or large-scale Streambed verification) or to execute Nexmark queries. The notebooks are the following:

- [xp_datagen](./xp_datagen_2HY61EX49.zpln): notebook used for large-scale experiments to check the results of Streambed. Injects in Kafka at the given rate Nexmark data.
- [xp_intro_init_kafka](./xp_intro_init_kafka_2J1RECAWT.zpln): initialization of data in Kafka for Streambed. This script is automatically called by the notebooks.
- Streambed queries notebooks contain in their file names `kafka_custom_ratelimit`
- Test queries (used to evaluate Streambed results) files contain either `kafka` when using the Kafka source (`q5`, `q8`, `q11`) or `datagen` when using the Nexmark datagen source (`q1`, `q2`).

All notebooks share the same architecture, with the following cells:

- Flink package configuration: setting of the target Flink endpoint, needed packages, and Flink expected parameters for Nexmark
- Kafka table creation (query specific): customizable Kafka source `CREATE TABLE` operation
- Datagen table creation (query specific): customizable Datagen source `CREATE TABLE` operation
- Sink initialization (query specific): Sink `CREATE TABLE` operation
- Target query parallelism setting and execution comprising the target query. This cell is developed in Scala.

Some of the cells have parameters initialized by Streambed, such as:

- the bootstrap URI, topic, and rate limit of the Kafka source (Kafka table creation)
- if used, the datagen rate, number of events, entity distribution, and target table name (kafka or datagen) (Datagen table creation)
- the parallelism affected to each task as provided by the CO module, the default parallelism if not defined, the number of sources, and the job name (Target query parallelism setting and execution)

Since most of the code is shared, an harmonization in a unique notebook is planned shortly: the table creation and the target SQL query will be then passed as parameters.
