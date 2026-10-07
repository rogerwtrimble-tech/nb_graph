{{- define "nbg.fullname" -}}
{{- if contains .Chart.Name .Release.Name -}}{{ .Release.Name | trunc 50 | trimSuffix "-" }}
{{- else -}}{{ printf "%s-%s" .Release.Name .Chart.Name | trunc 50 | trimSuffix "-" }}{{- end -}}
{{- end -}}

{{- define "nbg.name" -}}{{ include "nbg.fullname" .root }}-{{ .component }}{{- end -}}

{{- define "nbg.labels" -}}
app.kubernetes.io/name: nb-graph
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/version: {{ .root.Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .root.Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .root.Chart.Name .root.Chart.Version }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "nbg.selector" -}}
app.kubernetes.io/name: nb-graph
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{/* image: registry prefix applies to nb_graph/* and upstream images alike */}}
{{- define "nbg.image" -}}
{{- $reg := .root.Values.image.registry -}}
{{- if $reg -}}{{ printf "%s/%s:%s" (trimSuffix "/" $reg) (.img.repository | trimPrefix "docker.io/") (toString .img.tag) }}
{{- else -}}{{ printf "%s:%s" .img.repository (toString .img.tag) }}{{- end -}}
{{- end -}}

{{- define "nbg.secretName" -}}
{{- .Values.secrets.existingSecret | default (printf "%s-secrets" (include "nbg.fullname" .)) -}}
{{- end -}}

{{- define "nbg.netboxPublicUrl" -}}
{{- if .Values.netbox.publicUrl -}}{{ .Values.netbox.publicUrl }}
{{- else if .Values.ingress.enabled -}}{{ ternary "https" "http" (gt (len .Values.ingress.tls) 0) }}://{{ .Values.ingress.netboxHost }}
{{- else -}}http://localhost:{{ .Values.service.netboxPort }}{{- end -}}
{{- end -}}

{{- define "nbg.uiPublicUrl" -}}
{{- if .Values.ingress.enabled -}}{{ ternary "https" "http" (gt (len .Values.ingress.tls) 0) }}://{{ .Values.ingress.uiHost }}
{{- else -}}http://localhost:{{ .Values.service.uiPort }}{{- end -}}
{{- end -}}

{{- define "nbg.pod" -}}
{{- with .Values.image.pullSecrets }}
imagePullSecrets: {{- toYaml . | nindent 2 }}
{{- end }}
{{- with .Values.nodeSelector }}
nodeSelector: {{- toYaml . | nindent 2 }}
{{- end }}
{{- with .Values.tolerations }}
tolerations: {{- toYaml . | nindent 2 }}
{{- end }}
{{- with .Values.affinity }}
affinity: {{- toYaml . | nindent 2 }}
{{- end }}
{{- end -}}

{{/* secretKeyRef env entry */}}
{{- define "nbg.secretEnv" -}}
- name: {{ .name }}
  valueFrom: {secretKeyRef: {name: {{ include "nbg.secretName" .root }}, key: {{ .key }}}}
{{- end -}}

{{- define "nbg.waitFor" -}}
- name: wait-{{ .name }}
  image: {{ include "nbg.image" (dict "root" .root "img" .root.Values.postgres.image) }}
  imagePullPolicy: {{ .root.Values.image.pullPolicy }}
  command: ["sh", "-c", "until nc -z {{ .host }} {{ .port }}; do echo waiting for {{ .host }}:{{ .port }}; sleep 3; done"]
{{- end -}}
