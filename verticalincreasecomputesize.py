# Copyright (c) 2020 Oracle, Inc.
# Licensed under the Universal Permissive License v 1.0 as shown at https://oss.oracle.com/licenses/upl.

import io

import json
from telnetlib import STATUS
import time

import oci

from fdk import response


def instance_status(compute_client, instance_id):
    return compute_client.get_instance(instance_id).data.lifecycle_state

def instance_ocpu(compute_client,instance_id):
    return int(compute_client.get_instance(instance_id).data.shape_config.ocpus)


def instance_start(compute_client, instance_id):
    print('Starting Instance: {}'.format(instance_id))
    try:
        if instance_status(compute_client, instance_id) in 'STOPPED':
            try:
                resp = compute_client.instance_action(instance_id, 'START')
                print('Start response code: {0}'.format(resp.status))
            except oci.exceptions.ServiceError as e:
                print('Starting instance failed. {0}' .format(e))
                raise
        else:
            print('The instance was in the incorrect state to start' .format(instance_id))
            raise
    except oci.exceptions.ServiceError as e:
        print('Starting instance failed. {0}'.format(e))
        raise
    print('Started Instance: {}'.format(instance_id))
    return instance_status(compute_client, instance_id)


def increase_compute_shape(instance_id, alarm_msg_shape, cfg):
    instance_id = instance_id.split(",")
    ocpu = int(cfg["ocpu"])
    mem = int(cfg["mem"])
    lb = cfg["lb"]
    backendset = cfg["backendset"]
    signer = oci.auth.signers.get_resource_principals_signer()

    compute_client = oci.core.ComputeClient(config={}, signer=signer)
    #compute_client_composite = oci.core.ComputeClientCompositeOperations(compute_client)
    load_balancer_client = oci.load_balancer.LoadBalancerClient(
            config={}, signer=signer)
    for i in range(len(instance_id)):
       
        try:
            # Update flex instance size
            if instance_ocpu(compute_client,instance_id[i]) != ocpu:
                update_instance_details = oci.core.models.UpdateInstanceDetails(shape_config=oci.core.models.UpdateInstanceShapeConfigDetails(
                        ocpus=ocpu,
                        memory_in_gbs=mem))
                #resp = compute_client_composite.update_instance_and_wait_for_work_request(instance_id=instance_id[i],update_instance_details=update_instance_details)
                resp = compute_client.update_instance(
                    instance_id=instance_id[i], update_instance_details=update_instance_details)
                print(resp, flush=True)
            # Wait for status to be running
            while True:
                if instance_status(compute_client, instance_id[i]) in 'RUNNING':
                    try:
                        update_backend_set_response = load_balancer_client.update_backend_set(
                            update_backend_set_details=oci.load_balancer.models.UpdateBackendSetDetails(
                                policy="ROUND_ROBIN",
                                backends=[
                                    oci.load_balancer.models.BackendDetails(
                                        ip_address="10.0.1.167",
                                        port=80,
                                        weight=1,
                                        backup=False,
                                        drain=False,
                                        offline=False),
                                    oci.load_balancer.models.BackendDetails(
                                        ip_address="10.0.1.109",
                                        port=80,
                                        weight=1,
                                        backup=False,
                                        drain=False,
                                        offline=False)],
                                health_checker=oci.load_balancer.models.HealthCheckerDetails(
                                    protocol="HTTP",
                                    url_path="/",
                                    port=80,
                                    return_code=200,
                                    retries=3,
                                    timeout_in_millis=3000,
                                    interval_in_millis=10000)),
                            load_balancer_id=lb,
                            backend_set_name=backendset
                        )
                        print(update_backend_set_response, flush=True)
                        break
                    except Exception as ex1:
                        print('ERROR: cannot update backend set', ex1, flush=True)
                elif instance_status(compute_client, instance_id[i]) in 'STOPPED':
                    time.sleep(60)
                    instance_start(compute_client, instance_id[i])
                    continue
                else:
                    continue
        except Exception as ex:
            print('ERROR: cannot update instance {}'.format(instance_id[i]), flush=True)
            raise
    return "The shape of Instance {} is updated, the instance is rebooting...".format(instance_id[i])


def handler(ctx, data: io.BytesIO = None):
    cfg = ctx.Config()
    alarm_msg = {}
    # Getting values from function configuration
    instance_id = cfg["instance_id"]

    try:
        headers = ctx.Headers()
    except Exception as ex:
        print('ERROR: Missing Message ID in the header', ex, flush=True)
        raise
    try:
        alarm_msg = json.loads(data.getvalue())
        print("INFO: Alarm message: ")
        print(alarm_msg, flush=True)
    except (Exception, ValueError) as ex:
        print(str(ex), flush=True)

    if alarm_msg["type"] == "OK_TO_FIRING":
        if alarm_msg["alarmMetaData"][0]["dimensions"]:
            # assuming the first dimension matches the instance to resize
            alarm_metric_dimension = alarm_msg["alarmMetaData"][0]["dimensions"][0]
            print("INFO: Instance to resize: ",
                  alarm_metric_dimension["resourceId"], flush=True)
            func_response = increase_compute_shape(
                instance_id, alarm_metric_dimension["shape"], cfg)
            print("INFO: ", func_response, flush=True)
        else:
            print('ERROR: There is no metric dimension in this alarm message', flush=True)
            func_response = "There is no metric dimension in this alarm message"
    else:
        print('INFO: Nothing to do, alarm is not FIRING', flush=True)
        func_response = "Nothing to do, alarm is not FIRING"

    return response.Response(
        ctx,
        response_data=func_response,
        headers={"Content-Type": "application/json"}
    )
