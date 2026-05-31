{{/*
Expand the name of the chart.
*/}}
{{- define "rag-platform.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "rag-platform.fullname" -}}
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
{{- define "rag-platform.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "rag-platform.labels" -}}
helm.sh/chart: {{ include "rag-platform.chart" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: rag-platform
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}

{{/*
Selector labels for a specific component
Usage: {{ include "rag-platform.selectorLabels" (dict "component" "api-gateway") }}
*/}}
{{- define "rag-platform.selectorLabels" -}}
app: {{ .component }}
{{- end }}

{{/*
Component labels (common + selector)
Usage: {{ include "rag-platform.componentLabels" (dict "component" "api-gateway" "context" .) }}
*/}}
{{- define "rag-platform.componentLabels" -}}
{{ include "rag-platform.labels" .context }}
{{ include "rag-platform.selectorLabels" (dict "component" .component) }}
{{- end }}

{{/*
Namespace helper
*/}}
{{- define "rag-platform.namespace" -}}
{{- .Values.global.namespace | default .Release.Namespace }}
{{- end }}

{{/*
ConfigMap name
*/}}
{{- define "rag-platform.configMapName" -}}
{{- printf "%s-config" (include "rag-platform.fullname" .) }}
{{- end }}

{{/*
Secret name
*/}}
{{- define "rag-platform.secretName" -}}
{{- printf "%s-secrets" (include "rag-platform.fullname" .) }}
{{- end }}

{{/*
Image helper
Usage: {{ include "rag-platform.image" (dict "registry" .Values.global.imageRegistry "repository" .Values.apiGateway.image.repository "tag" .Values.apiGateway.image.tag) }}
*/}}
{{- define "rag-platform.image" -}}
{{- if .registry }}
{{- printf "%s/%s:%s" .registry .repository (.tag | default "latest") }}
{{- else }}
{{- printf "%s:%s" .repository (.tag | default "latest") }}
{{- end }}
{{- end }}
