#!/bin/bash

export ZEPPELIN_POD=`kubectl get pods -n manager -o=name | grep zeppelin | sed "s/^.\{4\}//"` 
kubectl wait -n manager pod/$ZEPPELIN_POD --for condition=Ready --timeout=600s
#export MANAGER_NODE=`kubectl get node --show-labels |grep tier=manager | awk '{print $1}'` # G5K: use node name
export MANAGER_NODE=`kubectl get nodes --selector=tier=manager -o jsonpath='{$.items[*].status.addresses[?(@.type=="InternalIP")].address}'` # kind : use node IP

kubectl -n manager exec $ZEPPELIN_POD -- wget -P /tmp https://repo.maven.apache.org/maven2/org/apache/flink/flink-sql-connector-kafka_2.12/1.14.2/flink-sql-connector-kafka_2.12-1.14.2.jar
# nexmark and the rate limit connector should be both in the tmp directory
kubectl cp -n manager ../../tmp/flink-sql-connector-kafka-ratelimit_2.12-1.14.2.jar $ZEPPELIN_POD:/tmp/flink-sql-connector-kafka-ratelimit_2.12-1.14.2.jar
kubectl cp -n manager ../../tmp/nexmark-flink-0.2-SNAPSHOT.jar $ZEPPELIN_POD:/tmp/nexmark-flink-0.2-SNAPSHOT.jar
# upload zeppelin notebooks
for FILE in ../../experiments/streambed-nexmark/zeppelin/*.zpln; do echo $FILE; curl ${MANAGER_NODE}:30088/api/notebook/import -d @$FILE; done
# set Flink interpreter to isolated mode (with default parameters)
curl -X PUT  ${MANAGER_NODE}:30088/api/interpreter/setting/flink -H 'Content-Type: application/json' -d @../common/zeppelin-flink-config.json
# remove from 
kubectl -n manager exec $ZEPPELIN_POD  -- rm /opt/flink/lib/flink-connector-kafka_2.12-1.14.2.jar
kubectl -n manager exec $ZEPPELIN_POD  -- rm /opt/flink/lib/flink-sql-connector-kafka_2.12-1.14.2.jar
curl -u "admin:prom-operator" -X POST ${MANAGER_NODE}:30300/api/dashboards/import -H 'Content-Type: application/json' -d "{\"Dashboard\":$(cat ../common/grafana.json)}"