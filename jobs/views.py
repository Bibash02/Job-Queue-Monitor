from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from . import services
from .models import Job, JobStatus, JobType
from .serializers import JobCreateSerializer, JobDetailSerializer, JobSerializer


class JobViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Staff-only API. Filter with ?status=failed&job_type=email."""

    queryset = Job.objects.all()

    def get_serializer_class(self):
        return JobDetailSerializer if self.action == "retrieve" else JobSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        for field in ("status", "job_type"):
            value = self.request.query_params.get(field)
            if value:
                qs = qs.filter(**{field: value})
        return qs.prefetch_related("attempt_logs") if self.action == "retrieve" else qs

    def create(self, request):
        ser = JobCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        job = services.enqueue(**ser.validated_data)
        return Response(JobSerializer(job).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        try:
            job = services.retry_now(self.get_object())
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(JobSerializer(job).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        try:
            job = services.cancel(self.get_object())
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(JobSerializer(job).data)

    @action(detail=False, methods=["get"])
    def stats(self, request):
        return Response(services.stats())


@staff_member_required
def dashboard(request):
    qs = Job.objects.all()
    status_filter = request.GET.get("status", "")
    type_filter = request.GET.get("job_type", "")
    if status_filter:
        qs = qs.filter(status=status_filter)
    if type_filter:
        qs = qs.filter(job_type=type_filter)
    return render(request, "jobs/dashboard.html", {
        "stats": services.stats(),
        "jobs": qs.order_by("-id")[:50],
        "failing": Job.objects.filter(status__in=[JobStatus.FAILED, JobStatus.RETRYING]).order_by("-id")[:10],
        "statuses": JobStatus.choices,
        "types": JobType.choices,
        "status_filter": status_filter,
        "type_filter": type_filter,
    })
