from rest_framework import serializers

from .models import Job, JobAttempt, JobType


class JobAttemptSerializer(serializers.ModelSerializer):
    duration = serializers.FloatField(read_only=True)

    class Meta:
        model = JobAttempt
        fields = ["number", "worker", "started_at", "finished_at", "duration",
                  "success", "error_message", "traceback"]


class JobSerializer(serializers.ModelSerializer):
    duration = serializers.FloatField(read_only=True)

    class Meta:
        model = Job
        fields = ["id", "job_type", "status", "attempts", "max_attempts", "error_message",
                  "created_at", "next_run_at", "started_at", "finished_at", "duration"]
        read_only_fields = fields


class JobDetailSerializer(JobSerializer):
    attempt_logs = JobAttemptSerializer(many=True, read_only=True)

    class Meta(JobSerializer.Meta):
        fields = JobSerializer.Meta.fields + ["payload", "result", "locked_by", "attempt_logs"]
        read_only_fields = fields


class JobCreateSerializer(serializers.Serializer):
    job_type = serializers.ChoiceField(choices=JobType.choices)
    payload = serializers.JSONField(required=False, default=dict)
    max_attempts = serializers.IntegerField(required=False, min_value=1, max_value=10)
    delay_seconds = serializers.IntegerField(required=False, min_value=0, default=0)
