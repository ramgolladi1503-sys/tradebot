#!/usr/bin/env python3
from __future__ import annotations
import re

JOB_ID=re.compile(r'^[0-9a-f]{32}$')
SHA64=re.compile(r'^[0-9a-f]{64}$')
ROLE_ID=re.compile(r'^[RA][0-9]{2,3}$')


def validate_bridge_receipt(receipt: object, artifact: object, *, candidate_head: str, job_type: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(receipt, dict):
        return ['RECEIPT_OBJECT_REQUIRED']
    if not isinstance(artifact, dict):
        return ['ARTIFACT_OBJECT_REQUIRED']
    if receipt.get('runtime_authority') != 'NONE':
        errors.append('RECEIPT_RUNTIME_AUTHORITY_INVALID')
    if receipt.get('broker_actions_allowed') is not False:
        errors.append('RECEIPT_BROKER_BOUNDARY_INVALID')
    worker=receipt.get('worker_id')
    if not isinstance(worker,str) or not worker.strip():
        errors.append('RECEIPT_WORKER_ID_MISSING')
    req=receipt.get('request');job=receipt.get('job')
    if not isinstance(req,dict): errors.append('RECEIPT_REQUEST_INVALID');req={}
    if not isinstance(job,dict): errors.append('RECEIPT_JOB_INVALID');job={}
    if req.get('candidate_sha') != candidate_head or job.get('candidate_sha') != candidate_head:
        errors.append('RECEIPT_HEAD_MISMATCH')
    if req.get('job_type') != job_type or job.get('job_type') != job_type:
        errors.append('RECEIPT_JOB_TYPE_MISMATCH')
    role_id=artifact.get('execution_role_id')
    if not isinstance(role_id,str) or not ROLE_ID.fullmatch(role_id):
        errors.append('ARTIFACT_EXECUTION_ROLE_INVALID')
    elif req.get('role_id') != role_id or job.get('role_id') != role_id:
        errors.append('RECEIPT_ROLE_MISMATCH')
    job_id=artifact.get('execution_job_id')
    if not isinstance(job_id,str) or not JOB_ID.fullmatch(job_id):
        errors.append('ARTIFACT_EXECUTION_JOB_INVALID')
    elif job.get('job_id') != job_id:
        errors.append('RECEIPT_JOB_ID_MISMATCH')
    if artifact.get('transport') != 'mac_git_mailbox':
        errors.append('ARTIFACT_TRANSPORT_INVALID')
    if artifact.get('runtime_authority') != 'NONE':
        errors.append('ARTIFACT_RUNTIME_AUTHORITY_INVALID')
    if artifact.get('broker_actions') != 'NONE':
        errors.append('ARTIFACT_BROKER_BOUNDARY_INVALID')
    if job.get('state') != 'SUCCEEDED' or job.get('exit_code') != 0:
        errors.append('RECEIPT_JOB_NOT_SUCCESSFUL')
    command_hash=job.get('command_hash')
    if not isinstance(command_hash,str) or not SHA64.fullmatch(command_hash):
        errors.append('RECEIPT_COMMAND_HASH_INVALID')
    output_path=artifact.get('output_path')
    if not isinstance(output_path,str) or not output_path.strip():
        errors.append('ARTIFACT_OUTPUT_PATH_INVALID')
    elif req.get('output_path') != output_path or job.get('output_path') != output_path:
        errors.append('RECEIPT_OUTPUT_PATH_MISMATCH')
    packet_path=artifact.get('packet_path')
    if not isinstance(packet_path,str) or not packet_path.strip():
        errors.append('ARTIFACT_PACKET_PATH_INVALID')
    elif req.get('packet_path') != packet_path or job.get('packet_path') != packet_path:
        errors.append('RECEIPT_PACKET_PATH_MISMATCH')
    times=[job.get('created_at'),job.get('started_at'),job.get('finished_at')]
    if any(isinstance(x,bool) or not isinstance(x,(int,float)) for x in times):
        errors.append('RECEIPT_TIMESTAMPS_INVALID')
    elif not (times[0] <= times[1] <= times[2]):
        errors.append('RECEIPT_TEMPORAL_ORDER_INVALID')
    return errors
