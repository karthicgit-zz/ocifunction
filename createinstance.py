import io
import json
import os
from fdk import response
from fdk import context

import oci

def handler(ctx, data: io.BytesIO=None):
    cfg = ctx.Config()
    signer = oci.auth.signers.get_resource_principals_signer()
    identity_client = oci.identity.IdentityClient(config={}, signer=signer)
    availability_domain = get_availability_domain(identity_client, signer.compartment_id)
    launch_instance_details = oci.core.models.LaunchInstanceDetails(
        display_name=cfg["displayname"],
        compartment_id=signer.compartment_id,
        availability_domain=availability_domain.name,
        shape=cfg["shape"],
        shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(ocpus=1,memory_in_gbs=10),
        subnet_id=cfg["subnet"],
        image_id=cfg["imageid"],
        preemptible_instance_config=oci.core.models.PreemptibleInstanceConfigDetails(preemption_action=oci.core.models.TerminatePreemptionAction(preserve_boot_volume=False))
    )
    resp = launch_instances(signer,launch_instance_details)
    return response.Response(
        ctx,
        response_data=json.dumps({"status": "Success"}),
        headers={"Content-Type": "application/json"}
    )

# List instances ---------------------------------------------------------------
def launch_instances(signer,launch_instance_details):
    client = oci.core.ComputeClient(config={}, signer=signer)
    # OCI API to manage Compute resources such as compute instances, block storage volumes, etc.
    try:
        # Returns a list of all instances in the current compartment
        inst = client.launch_instance(launch_instance_details)
    except Exception as ex:
        print("ERROR: accessing Compute instances failed", ex, flush=True)
        raise

    return inst.data

def get_availability_domain(identity_client, compartment_id):
    list_availability_domains_response = oci.pagination.list_call_get_all_results(
        identity_client.list_availability_domains,
        compartment_id
    )
    availability_domain = list_availability_domains_response.data[0]

    print('Running in Availability Domain: {}'.format(availability_domain.name))

    return availability_domain
