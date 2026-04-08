{{/*
Expand the name of the chart.
*/}}
{{- define "clinigraph.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "clinigraph.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Chart label
*/}}
{{- define "clinigraph.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "clinigraph.labels" -}}
helm.sh/chart: {{ include "clinigraph.chart" . }}
{{ include "clinigraph.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "clinigraph.selectorLabels" -}}
app.kubernetes.io/name: {{ include "clinigraph.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Image helper – prepends global registry, uses per-service tag or falls back to global.imageTag.
Usage: {{ include "clinigraph.image" (dict "global" .Values.global "image" .Values.web.image) }}
*/}}
{{- define "clinigraph.image" -}}
{{- $registry := .global.imageRegistry -}}
{{- $repo     := .image.repository -}}
{{- $tag      := coalesce .image.tag .global.imageTag "latest" -}}
{{- if $registry -}}
{{- printf "%s/%s:%s" $registry $repo $tag -}}
{{- else -}}
{{- printf "%s:%s" $repo $tag -}}
{{- end -}}
{{- end }}

{{/*
StorageClass helper – falls back through service→global→cluster default.
Usage: {{ include "clinigraph.storageClass" (dict "global" .Values.global "storage" .Values.weaviate.storage) }}
*/}}
{{- define "clinigraph.storageClass" -}}
{{- coalesce .storage.storageClass .global.storageClass "" -}}
{{- end }}

{{/*
Database URL (postgres DSN).
Uses in-cluster postgres unless externalDatabase.enabled=true.
*/}}
{{- define "clinigraph.databaseUrl" -}}
{{- if .Values.externalDatabase.enabled -}}
postgresql://{{ .Values.externalDatabase.username }}:$(DJANGO_DB_PASSWORD)@{{ .Values.externalDatabase.host }}:{{ .Values.externalDatabase.port }}/{{ .Values.externalDatabase.database }}
{{- else -}}
postgresql://{{ .Values.postgres.auth.username }}:$(DJANGO_DB_PASSWORD)@{{ include "clinigraph.fullname" . }}-postgres:5432/{{ .Values.postgres.auth.database }}
{{- end -}}
{{- end }}

{{/*
Redis URL – uses in-cluster redis unless externalRedis.enabled=true.
*/}}
{{- define "clinigraph.redisUrl" -}}
{{- if .Values.externalRedis.enabled -}}
{{ .Values.externalRedis.url }}
{{- else -}}
redis://{{ include "clinigraph.fullname" . }}-redis:6379/0
{{- end -}}
{{- end }}

{{/*
Weaviate host (internal service name).
*/}}
{{- define "clinigraph.weaviateHost" -}}
{{- include "clinigraph.fullname" . }}-weaviate
{{- end }}

{{/*
Ollama base URL.
*/}}
{{- define "clinigraph.ollamaUrl" -}}
http://{{ include "clinigraph.fullname" . }}-ollama:11434
{{- end }}

{{/*
Kafka bootstrap servers.
*/}}
{{- define "clinigraph.kafkaBootstrap" -}}
{{- include "clinigraph.fullname" . }}-kafka:9092
{{- end }}

{{/*
Secret name – uses existingSecret if provided, else chart-generated secret.
*/}}
{{- define "clinigraph.secretName" -}}
{{- if .Values.secrets.existingSecret -}}
{{- .Values.secrets.existingSecret -}}
{{- else -}}
{{- include "clinigraph.fullname" . }}-secrets
{{- end -}}
{{- end }}
