import requests 
    
from graphlib import TopologicalSorter
from tqdm.auto import tqdm

from time import sleep
from common import *
from common_k8s import *
import common
from kubernetes import client, config
import logging
import pkg_resources

request_input_throughput = 'sum(irate(flink_taskmanager_job_task_operator_numRecordsIn{{task_id=~"{}", job_id="{}"}}[15s]))'
request_output_throughput = 'sum(irate(flink_taskmanager_job_task_operator_numRecordsOut{{task_id=~"{}", job_id="{}"}}[15s]))'
request_busy = 'sum(flink_taskmanager_job_task_busyTimeMsPerSecond{{task_id=~"{}", subtask_index=~"{}", job_id="{}"}})'
request_busy_avg = 'avg(flink_taskmanager_job_task_busyTimeMsPerSecond{{task_id=~"{}", subtask_index=~"{}", job_id="{}"}})'
request_backpressured_avg = 'avg(flink_taskmanager_job_task_backPressuredTimeMsPerSecond{{task_id=~"{}", subtask_index=~"{}", job_id="{}"}})'
request_source_througput = 'sum(irate(flink_taskmanager_job_task_operator_numRecordsOut{{task_name=~"Source.*", job_id="{}"}}[15s]))'
request_sink_throughput = 'sum(irate(flink_taskmanager_job_task_operator_numRecordsIn{{task_name=~"Sink.*", job_id="{}"}}[15s]))'

logger = logging.getLogger('streambed')

def get_service_public_address(namespace, node_tier, service_name, port):
    # Get address
    from kubernetes import client, config

    # Configs can be set in Configuration class directly or using helper utility
    config.load_kube_config()
    api_instance = client.CoreV1Api()

    # Listing the cluster nodes
    node_list = api_instance.list_node()
    label_master = "node-role.kubernetes.io/controlplane"
    label_worker = "node-role.kubernetes.io/worker"
    count = 0
    manager_node = None
    jobmanager_node = None
    taskmanager_nodes = []
    for i, node in enumerate(node_list.items):
        if "tier" in node.metadata.labels and node.metadata.labels["tier"] == node_tier:
            jobmanager_node_name = node.metadata.name
            address = [address.address for address in node.status.addresses if address.type=="InternalIP"][0]
            jobmanager_node = address
    service_list = api_instance.read_namespaced_service(namespace=namespace, name=service_name)
    for port_desc in service_list.spec.ports:
        if port_desc.port==port:
            jobmanager_port = port_desc.node_port
    return ("http://{}:{}".format(jobmanager_node, jobmanager_port), "http://{}:{}".format(jobmanager_node_name, jobmanager_port))

def delete_flink_cluster(name, namespace="default"):
    with client.ApiClient(k8s_configuration) as api_client:
        # Create an instance of the API class
        api_instance = client.CustomObjectsApi(api_client)

    try:
        api_instance.delete_namespaced_custom_object(
            group = "flinkoperator.k8s.io",
            version = "v1beta1",
            namespace = namespace,
            plural = "flinkclusters",
            name = name
        )
    except:
        logger.error("Error while removing {} (ns: {})".format(name, namespace))

def get_job_info(job_id, base_url=None):
    if base_url is None:
        base_url = common.flink_base_url     
    r = requests.get(base_url + "/jobs/" + job_id)
    job = r.json()
    start_time = job["start-time"]
    duration = job["duration"]
    source_vertex = None
    for vertex in job["vertices"]:
        if "Source" in vertex["name"]:
            source_vertex = vertex
            break
    return (start_time, duration, job)

def cancel_job(job_id, base_url=None):
    if base_url is None:
        base_url = common.flink_base_url    
    r = requests.patch(base_url + "/jobs/" + job_id + "?mode=cancel")
    if r.status_code == 202:
        return True
    else:
        return False

def get_task_managers(base_url=None):
    if base_url is None:
        base_url = common.flink_base_url
    try:
        r = requests.get(base_url + "/taskmanagers")
    except:
        return []
    
    status_code = r.status_code
    if status_code == 200:
        return r.json()["taskmanagers"]
    else:
        return []

def wait_for_task_managers(task_managers_qty, base_url=None, timeout=600):
    if base_url is None:
        base_url = common.flink_base_url    
    
    current_task_managers_qty = len(get_task_managers(base_url))
    with tqdm(total=task_managers_qty) as pbar:
        pbar.set_description("Flink TM initialization")
        while current_task_managers_qty != task_managers_qty:
            current_task_managers_qty = len(get_task_managers(base_url))
            pbar.update(current_task_managers_qty- pbar.n)
            sleep(5)


def deploy_datagen(cpu=16, memory=16*1024, task_managers_qty=2, task_slots=16, node_selector="jobmanager"):

    deploy("datagen", flink_gen_configuration(cpu=cpu, memory=memory, task_managers=task_managers_qty, evenly_spread="true", custom_memory=None, task_slots=task_slots, host="datagen-flink.127-0-0-1.sslip.io", node_selector=node_selector))

    sleep(10)
    if common.dynamic_flink_url:
        (common.datagen_flink_base_url, _) = get_service_public_address("default", "jobmanager", "datagen-flink-jobmanager", 8081)
    else:
        common.datagen_flink_base_url = "http://datagen-flink.127-0-0-1.sslip.io:30080"
    wait_for_task_managers(task_managers_qty, common.datagen_flink_base_url)
    return common.datagen_flink_base_url



def deploy_sut(m):
    # loop infra Flink
    (cpu, 
    memory, 
    task_managers_qty,
    #run, 
    task_slots_per_task_manager, 
    #source_parallelism, 
    #parallelism, 
    evenly_spread, 
    #task_slot_limit
    ) = (
        m["cpu"], 
        m["memory"], 
        m["task_managers_qty"],
        #m["run"], 
        m["task_slots_per_task_manager"], 
        #m["source_parallelism"], 
        #m["parallelism"], 
        m["evenly_spread"], 
        #m["task_slots_limit"]
    )

    deploy("nexmark", flink_configuration(
        cpu=cpu,
        memory=memory,
        task_managers=task_managers_qty, 
        task_slots=task_slots_per_task_manager, 
        evenly_spread=evenly_spread))

    sleep(10)
    if common.dynamic_flink_url:
        (common.flink_base_url, _) = get_service_public_address("default", "jobmanager", "nexmark-flink-jobmanager", 8081)
    else:
        common.flink_base_url = "http://flink.127-0-0-1.sslip.io:30080"

    wait_for_task_managers(task_managers_qty, common.flink_base_url)
    return common.flink_base_url

def get_jobid_by_name(name, state=None, base_url=None):
    if base_url is None:
        base_url = common.flink_base_url
    r = requests.get(base_url + "/jobs/")
    payload = r.json()
    array = []
    for job in payload["jobs"]:
        id = job["id"]
        r = requests.get(base_url + "/jobs/" + id)
        job_payload = r.json()
        if state is None:
            array.append(id)
        else:
            if job_payload["name"] == name and job_payload["state"] == state:
                array.append(id)
    return array

def get_job_operators_topological_order(job_id):
    r = requests.get(common.flink_base_url + "/jobs/" + job_id+ "/plan")
    job = r.json()
    nodes = [node["id"] for node in job["plan"]["nodes"]]
    nodes_labels = [node for node in job["plan"]["nodes"]]

    map_id_name = dict(zip(nodes, nodes_labels))


    graph_job = {}
    for node in job["plan"]["nodes"]:
        #print(node)
        if "inputs" in node:
            graph_job[node["id"]] = [input["id"] for input in node["inputs"]]
        else: 
            graph_job[node["id"]] = []
    #print(graph_job)    
    ts = TopologicalSorter(graph_job)

    return [map_id_name[x] for x in tuple(ts.static_order())]

def deploy(name, configuration): 
    #TODO: change this by direct FlinkCluster CR creation + Ingress
    chart_path = pkg_resources.resource_filename('streambed', 'charts/flink')
    logger.info("Deploying Flink  {}".format(configuration))
    chart_instance = name
    uninstall_chart(chart_instance)
    sleep(10)
    install_chart(chart_path, chart_instance, configuration)
  
    return chart_instance + "-flink-jobmanager"

def flink_configuration(cpu, memory, task_managers=4, task_slots=1, evenly_spread="false", custom_memory=None):
    if custom_memory is None:
        configuration = {
                "cpu": cpu * 1000,
                "memory": memory,
                "replicas": task_managers,
                "task_slots": task_slots,
                "evenly_spread": evenly_spread,
            }

        template = {
            "image!repository": "flink",
            "image!tag": "1.14.2",
            "taskManager.replicas": "{0[replicas]}",
            "flinkProperties!taskmanager!numberOfTaskSlots": "{0[task_slots]}",

            "jobManager!resources!limits!memory": "4096Mi",
            "jobManager!resources!limits!cpu": "4000m",
            "flinkProperties!jobmanager!memory!process!size": "4g",
            "taskManager!resources!limits!memory": "{0[memory]}Mi",
            "taskManager!resources!limits!cpu": "{0[cpu]}m",
            "taskManager!resources!limits!memory": "{0[memory]}Mi",
            "flinkProperties!taskmanager!memory!process!size": "{0[memory]}m",
            "flinkProperties!evenlySpreadOutSlots": "{0[evenly_spread]}",
        }
    else:
        memory = sum([int(custom_memory[x]) for x in custom_memory])

        configuration = {
                "cpu": cpu * 1000,
                "memory": memory,
                "replicas": task_managers,
                "task_slots": task_slots,
                "evenly_spread": evenly_spread,
            }
        configuration.update(custom_memory)
        template = {
            "image!repository": "flink",
            "image!tag": "1.14.2",
            "taskManager.replicas": "{0[replicas]}",
            "flinkProperties!taskmanager!numberOfTaskSlots": "{0[task_slots]}",

            "jobManager!resources!limits!memory": "4096Mi",
            "jobManager!resources!limits!cpu": "4000m",
            "flinkProperties!jobmanager!memory!process!size": "4g",
            "taskManager!resources!limits!memory": "{0[memory]}Mi",
            "taskManager!resources!limits!cpu": "{0[cpu]}m",
            "taskManager!resources!limits!memory": "{0[memory]}Mi",
#            "flinkProperties!taskmanager!memory!process!size": "{0[memory]}m",
            "flinkProperties!evenlySpreadOutSlots": "{0[evenly_spread]}",
            "flinkProperties!taskmanager!memory!custom!framework_heap": "{0[framework_heap]}m",
            "flinkProperties!taskmanager!memory!custom!heap": "{0[heap]}m",
            "flinkProperties!taskmanager!memory!custom!managed": "{0[managed]}m",
            "flinkProperties!taskmanager!memory!custom!framework_off_heap": "{0[framework_off_heap]}m",
            "flinkProperties!taskmanager!memory!custom!task_off_heap": "{0[task_off_heap]}m",
            "flinkProperties!taskmanager!memory!custom!network": "{0[network]}m",
            "flinkProperties!taskmanager!memory!custom!metaspace": "{0[metaspace]}m",
            "flinkProperties!taskmanager!memory!custom!overhead": "{0[overhead]}m",
            "flinkProperties!taskmanager!memory!process!size": "{0[memory]}m",
        }
        
    for parameter in template:
        template[parameter] = template[parameter].format(configuration)

    
    return template

def flink_gen_configuration(cpu, memory, task_managers=4, task_slots=1, evenly_spread="false", host="flink", custom_memory=None, node_selector="jobmanager"):
    if custom_memory is None:
        configuration = {
                "cpu": cpu * 1000,
                "memory": memory,
                "replicas": task_managers,
                "task_slots": task_slots,
                "evenly_spread": evenly_spread,
                "host": host,
            }

        template = {
            "image!repository": "flink",
            "image!tag": "1.14.2",
            "taskManager.replicas": "{0[replicas]}",
            "flinkProperties!taskmanager!numberOfTaskSlots": "{0[task_slots]}",

            "jobManager!resources!limits!memory": "4096Mi",
            "jobManager!resources!limits!cpu": "4000m",
            "flinkProperties!jobmanager!memory!process!size": "4g",
            "taskManager!tier": node_selector,          
            "ingress!hosts[0]!host": "{0[host]}",              
            "ingress!hosts[0]!paths[0]!path": "/",
            "ingress!hosts[0]!paths[0]!pathType": "Prefix",
            "taskManager!resources!limits!memory": "{0[memory]}Mi",
            "taskManager!resources!limits!cpu": "{0[cpu]}m",
            "taskManager!resources!limits!memory": "{0[memory]}Mi",
            "flinkProperties!taskmanager!memory!process!size": "{0[memory]}m",
            "flinkProperties!evenlySpreadOutSlots": "{0[evenly_spread]}",
        }
    else:
        memory = sum([int(custom_memory[x]) for x in custom_memory])
        
        configuration = {
                "cpu": cpu * 1000,
                "memory": memory,
                "replicas": task_managers,
                "task_slots": task_slots,
                "evenly_spread": evenly_spread,
            }
        configuration.update(custom_memory)
        template = {
            "image!repository": "flink",
            "image!tag": "1.14.2",
            "taskManager.replicas": "{0[replicas]}",
            "flinkProperties!taskmanager!numberOfTaskSlots": "{0[task_slots]}",

            "jobManager!resources!limits!memory": "4096Mi",
            "jobManager!resources!limits!cpu": "4000m",
            "flinkProperties!jobmanager!memory!process!size": "4g",
            "taskManager!nodeSelector!tier": node_selector,
            "taskManager!resources!limits!memory": "{0[memory]}Mi",
            "taskManager!resources!limits!cpu": "{0[cpu]}m",
            "taskManager!resources!limits!memory": "{0[memory]}Mi",

            "flinkProperties!evenlySpreadOutSlots": "{0[evenly_spread]}",
            "flinkProperties!taskmanager!memory!custom!framework_heap": "{0[framework_heap]}m",
            "flinkProperties!taskmanager!memory!custom!heap": "{0[heap]}m",
            "flinkProperties!taskmanager!memory!custom!managed": "{0[managed]}m",
            "flinkProperties!taskmanager!memory!custom!framework_off_heap": "{0[framework_off_heap]}m",
            "flinkProperties!taskmanager!memory!custom!task_off_heap": "{0[task_off_heap]}m",
            "flinkProperties!taskmanager!memory!custom!network": "{0[network]}m",
            "flinkProperties!taskmanager!memory!custom!metaspace": "{0[metaspace]}m",
            "flinkProperties!taskmanager!memory!custom!overhead": "{0[overhead]}m",
            "flinkProperties!taskmanager!memory!process!size": "{0[memory]}m",
        }
        
    for parameter in template:
        template[parameter] = template[parameter].format(configuration)

    return template
