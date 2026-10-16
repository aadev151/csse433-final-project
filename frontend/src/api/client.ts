import type {
  Annotation,
  AnnotationInput,
  AnnotationTarget,
  AnnotationUpdate,
  ApiErrorBody,
  AuditRepairInput,
  AuditResult,
  Dataset,
  DatasetImportInput,
  DatasetImportResponse,
  Experiment,
  ExperimentFilters,
  ExperimentInput,
  FaultWindow,
  Health,
  LaunchResponse,
  LiveMessage,
  QueueState,
  ReadingsQuery,
  ReadingsResponse,
  Run,
  ServedBy,
  Signal,
  SignalInput,
  WriteResponse,
} from './types';

/** Every GET resolves to the data plus the store that answered (X-Served-By). */
export interface Served<T> {
  data: T;
  servedBy: ServedBy;
}

/** Thrown for any non-2xx response (or a network failure, with status 0). */
export class ApiError extends Error {
  readonly status: number;
  readonly body: ApiErrorBody | null;

  constructor(status: number, message: string, body: ApiErrorBody | null = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }

  get reason(): string | undefined {
    return this.body?.reason;
  }
}

export function isCassandraDown(err: unknown): boolean {
  return err instanceof ApiError && err.status === 503 && err.reason === 'cassandra_down';
}

export interface LiveHandlers {
  onOpen?: () => void;
  onMessage: (msg: LiveMessage) => void;
  /** Called when the socket closes or fails to connect. */
  onClose?: (reason: string) => void;
}

export interface LiveConnection {
  close: () => void;
}

export interface ApiClient {
  readonly mode: 'mock' | 'http';

  getHealth(): Promise<Served<Health>>;

  listDatasets(): Promise<Served<Dataset[]>>;
  importDatasets(body: DatasetImportInput): Promise<DatasetImportResponse>;
  deleteDataset(id: string): Promise<WriteResponse<null>>;

  listSignals(): Promise<Served<Signal[]>>;
  getSignal(id: string): Promise<Served<Signal>>;
  createSignal(body: SignalInput): Promise<WriteResponse<Signal>>;
  updateSignal(id: string, body: SignalInput): Promise<WriteResponse<Signal>>;
  deleteSignal(id: string): Promise<WriteResponse<null>>;

  listExperiments(filters?: ExperimentFilters): Promise<Served<Experiment[]>>;
  getExperiment(id: string): Promise<Served<Experiment>>;
  createExperiment(body: ExperimentInput): Promise<WriteResponse<Experiment>>;
  updateExperiment(id: string, body: ExperimentInput): Promise<WriteResponse<Experiment>>;
  deleteExperiment(id: string): Promise<WriteResponse<null>>;
  cloneExperiment(id: string): Promise<WriteResponse<Experiment>>;
  launchExperiment(id: string): Promise<LaunchResponse>;
  listRuns(experimentId: string): Promise<Served<Run[]>>;
  exportExperimentCsv(id: string): Promise<Blob>;

  getRun(id: string): Promise<Served<Run>>;
  cancelRun(id: string): Promise<WriteResponse<Run>>;
  getReadings(runId: string, query: ReadingsQuery): Promise<Served<ReadingsResponse>>;
  getFaults(runId: string): Promise<Served<FaultWindow[]>>;
  exportRunCsv(id: string): Promise<Blob>;
  openRunLive(runId: string, handlers: LiveHandlers): LiveConnection;

  getQueue(): Promise<Served<QueueState>>;

  listAnnotations(targetType: AnnotationTarget, targetId: string): Promise<Served<Annotation[]>>;
  createAnnotation(body: AnnotationInput): Promise<WriteResponse<Annotation>>;
  updateAnnotation(id: string, body: AnnotationUpdate): Promise<WriteResponse<Annotation>>;
  deleteAnnotation(id: string): Promise<WriteResponse<null>>;

  getAudit(): Promise<Served<AuditResult>>;
  repairAudit(body: AuditRepairInput): Promise<AuditResult>;
}
