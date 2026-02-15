import axios from "axios";
import type { ListLogsResponse, LogResponse } from "@/types/api";

const API_BASE_URL = import.meta.env.VITE_API_URL || "/api";
const API_KEY_STORAGE_KEY = "concordance_api_key";

// Helper to get the stored API key
function getStoredApiKey(): string | null {
  return localStorage.getItem(API_KEY_STORAGE_KEY);
}

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// Add request interceptor to include API key in all requests
api.interceptors.request.use((config) => {
  const apiKey = getStoredApiKey();
  if (apiKey) {
    config.headers["X-API-Key"] = apiKey;
  }
  return config;
});

// Error handler
export class ApiError extends Error {
  constructor(
    message: string,
    public status?: number,
    public details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface ApiErrorResponse {
  message?: string;
}

const handleApiError = (error: unknown): never => {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as ApiErrorResponse | undefined;
    throw new ApiError(
      data?.message || error.message,
      error.response?.status,
      error.response?.data,
    );
  }
  throw new ApiError("An unexpected error occurred");
};

// API Functions
export interface FetchLogsOptions {
  limit?: number;
  offset?: number;
  collectionId?: number;
  apiKey?: string;
}

export const fetchLogs = async (
  limit: number = 50,
  offset: number = 0,
  options?: { collectionId?: number; apiKey?: string },
): Promise<ListLogsResponse> => {
  try {
    const params: Record<string, unknown> = { limit, offset };
    if (options?.collectionId !== undefined) {
      params.collection_id = options.collectionId;
    }
    const config: { params: Record<string, unknown>; headers?: Record<string, string> } = { params };
    if (options?.apiKey !== undefined) {
      config.headers = { "X-API-Key": options.apiKey };
    }
    const response = await api.get<ListLogsResponse>("/logs", config);
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

// API Keys (for pseudo-collections)
export interface ApiKeySummary {
  api_key: string;
  request_count: number;
  latest_request_at: string;
}

export interface ListApiKeysResponse {
  api_keys: ApiKeySummary[];
  total: number;
}

export const listApiKeys = async (): Promise<ListApiKeysResponse> => {
  try {
    const response = await api.get<ListApiKeysResponse>("/logs/api-keys");
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

export const fetchLogDetail = async (
  requestId: string,
  options?: { apiKey?: string },
): Promise<LogResponse> => {
  try {
    const config: { headers?: Record<string, string> } = {};
    if (options?.apiKey !== undefined) {
      config.headers = { "X-API-Key": options.apiKey };
    }
    const response = await api.get<LogResponse>(`/logs/${requestId}`, config);
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

export const healthCheck = async (): Promise<boolean> => {
  try {
    await api.get("/health");
    return true;
  } catch {
    return false;
  }
};

export interface UpdateFavoriteResponse {
  request_id: string;
  favorited_by: string[];
  message: string;
}

export const addFavorite = async (
  requestId: string,
  name: string,
): Promise<UpdateFavoriteResponse> => {
  try {
    const response = await api.post<UpdateFavoriteResponse>(
      `/logs/${requestId}/favorite`,
      { name },
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

export const removeFavorite = async (
  requestId: string,
  name: string,
): Promise<UpdateFavoriteResponse> => {
  try {
    const response = await api.delete<UpdateFavoriteResponse>(
      `/logs/${requestId}/favorite`,
      { data: { name } },
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

// Tags API

export interface GetTagsResponse {
  request_id: string;
  tags: string[];
}

export interface UpdateTagResponse {
  request_id: string;
  tags: string[];
  message: string;
}

export const getTags = async (requestId: string): Promise<GetTagsResponse> => {
  try {
    const response = await api.get<GetTagsResponse>(`/logs/${requestId}/tags`);
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

export const addTag = async (
  requestId: string,
  tag: string,
): Promise<UpdateTagResponse> => {
  try {
    const response = await api.post<UpdateTagResponse>(
      `/logs/${requestId}/tags`,
      { tag },
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

export const removeTag = async (
  requestId: string,
  tag: string,
): Promise<UpdateTagResponse> => {
  try {
    const response = await api.delete<UpdateTagResponse>(
      `/logs/${requestId}/tags`,
      { data: { tag } },
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

// Discussions API

export interface Discussion {
  id: number;
  request_id: string;
  username: string;
  comment: string;
  created_at: string;
  updated_at: string;
}

export interface ListDiscussionsResponse {
  request_id: string;
  discussions: Discussion[];
  total: number;
  limit: number;
  offset: number;
}

export interface CreateDiscussionResponse {
  discussion: Discussion;
  message: string;
}

export interface UpdateDiscussionResponse {
  discussion: Discussion;
  message: string;
}

export interface DeleteDiscussionResponse {
  id: number;
  message: string;
}

export const listDiscussions = async (
  requestId: string,
  limit: number = 50,
  offset: number = 0,
): Promise<ListDiscussionsResponse> => {
  try {
    const response = await api.get<ListDiscussionsResponse>(
      `/logs/${requestId}/discussions`,
      { params: { limit, offset } },
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

export const createDiscussion = async (
  requestId: string,
  username: string,
  comment: string,
): Promise<CreateDiscussionResponse> => {
  try {
    const response = await api.post<CreateDiscussionResponse>(
      `/logs/${requestId}/discussions`,
      { username, comment },
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

export const updateDiscussion = async (
  requestId: string,
  discussionId: number,
  comment: string,
): Promise<UpdateDiscussionResponse> => {
  try {
    const response = await api.put<UpdateDiscussionResponse>(
      `/logs/${requestId}/discussions/${discussionId}`,
      { comment },
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

export const deleteDiscussion = async (
  requestId: string,
  discussionId: number,
): Promise<DeleteDiscussionResponse> => {
  try {
    const response = await api.delete<DeleteDiscussionResponse>(
      `/logs/${requestId}/discussions/${discussionId}`,
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

// Collections API

export interface Collection {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  created_by: string | null;
  is_public: boolean;
  public_token: string | null;
}

// Note: LogResponse from types/api.ts should also include is_public and public_token

export interface CollectionSummary extends Collection {
  request_count: number | null;
}

export interface CollectionRequest {
  request_id: string;
  added_at: string;
  added_by: string | null;
  notes: string | null;
  created_ts: string;
  finished_ts: string | null;
  model_id: string | null;
  final_text: string | null;
}

export interface ListCollectionsResponse {
  collections: CollectionSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface GetCollectionResponse {
  collection: Collection;
  requests: CollectionRequest[];
  total_requests: number;
}

export interface CreateCollectionResponse {
  collection: Collection;
  message: string;
}

export interface UpdateCollectionResponse {
  collection: Collection;
  message: string;
}

export interface DeleteCollectionResponse {
  id: number;
  message: string;
}

export interface AddRequestToCollectionResponse {
  collection_id: number;
  request_id: string;
  message: string;
}

export interface RemoveRequestFromCollectionResponse {
  collection_id: number;
  request_id: string;
  message: string;
}

export interface RequestCollectionsResponse {
  request_id: string;
  collections: CollectionSummary[];
}

export const listCollections = async (
  limit: number = 50,
  offset: number = 0,
): Promise<ListCollectionsResponse> => {
  try {
    const response = await api.get<ListCollectionsResponse>("/collections", {
      params: { limit, offset },
    });
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

export const getCollection = async (
  collectionId: number,
  limit: number = 50,
  offset: number = 0,
): Promise<GetCollectionResponse> => {
  try {
    const response = await api.get<GetCollectionResponse>(
      `/collections/${collectionId}`,
      { params: { limit, offset } },
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

export const createCollection = async (
  name: string,
  description?: string,
  createdBy?: string,
): Promise<CreateCollectionResponse> => {
  try {
    const response = await api.post<CreateCollectionResponse>("/collections", {
      name,
      description,
      created_by: createdBy,
    });
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

export const updateCollection = async (
  collectionId: number,
  name?: string,
  description?: string,
): Promise<UpdateCollectionResponse> => {
  try {
    const response = await api.put<UpdateCollectionResponse>(
      `/collections/${collectionId}`,
      { name, description },
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

export const deleteCollection = async (
  collectionId: number,
): Promise<DeleteCollectionResponse> => {
  try {
    const response = await api.delete<DeleteCollectionResponse>(
      `/collections/${collectionId}`,
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

export const addRequestToCollection = async (
  collectionId: number,
  requestId: string,
  addedBy?: string,
  notes?: string,
): Promise<AddRequestToCollectionResponse> => {
  try {
    const response = await api.post<AddRequestToCollectionResponse>(
      `/collections/${collectionId}/requests`,
      { request_id: requestId, added_by: addedBy, notes },
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

export const removeRequestFromCollection = async (
  collectionId: number,
  requestId: string,
): Promise<RemoveRequestFromCollectionResponse> => {
  try {
    const response = await api.delete<RemoveRequestFromCollectionResponse>(
      `/collections/${collectionId}/requests`,
      { data: { request_id: requestId } },
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

export const getRequestCollections = async (
  requestId: string,
): Promise<RequestCollectionsResponse> => {
  try {
    const response = await api.get<RequestCollectionsResponse>(
      `/logs/${requestId}/collections`,
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

export const addRequestToCollectionByRequest = async (
  requestId: string,
  collectionId: number,
  addedBy?: string,
  notes?: string,
): Promise<AddRequestToCollectionResponse> => {
  try {
    const response = await api.post<AddRequestToCollectionResponse>(
      `/logs/${requestId}/collections`,
      { collection_id: collectionId, added_by: addedBy, notes },
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

export const removeRequestFromCollectionByRequest = async (
  requestId: string,
  collectionId: number,
): Promise<RemoveRequestFromCollectionResponse> => {
  try {
    const response = await api.delete<RemoveRequestFromCollectionResponse>(
      `/logs/${requestId}/collections`,
      { data: { collection_id: collectionId } },
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

// Auth API

export interface ValidateKeyResponse {
  valid: boolean;
  name: string | null;
  allowed_api_key: string | null;
  is_admin: boolean;
  message: string;
}

export const validateApiKey = async (
  apiKey: string,
): Promise<ValidateKeyResponse> => {
  try {
    const response = await axios.get<ValidateKeyResponse>(
      `${API_BASE_URL}/auth/validate`,
      {
        headers: {
          "X-API-Key": apiKey,
        },
      },
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

export interface CurrentUserResponse {
  name: string;
  allowed_api_key: string | null;
  is_admin: boolean;
}

export const getCurrentUser = async (): Promise<CurrentUserResponse> => {
  try {
    const response = await api.get<CurrentUserResponse>("/auth/me");
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

// Public Collections API

export interface MakePublicResponse {
  collection_id: number;
  is_public: boolean;
  public_token: string | null;
  public_url: string | null;
  message: string;
}

export interface PublicCollectionInfo {
  id: number;
  name: string;
  description: string | null;
  created_at: string;
  request_count: number;
}

export interface PublicCollectionResponse {
  collection: PublicCollectionInfo;
  requests: CollectionRequest[];
  total_requests: number;
}

export const makeCollectionPublic = async (
  collectionId: number,
): Promise<MakePublicResponse> => {
  try {
    const response = await api.post<MakePublicResponse>(
      `/collections/${collectionId}/public`,
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

export const makeCollectionPrivate = async (
  collectionId: number,
): Promise<MakePublicResponse> => {
  try {
    const response = await api.delete<MakePublicResponse>(
      `/collections/${collectionId}/public`,
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

export const getPublicCollection = async (
  publicToken: string,
  limit: number = 50,
  offset: number = 0,
): Promise<PublicCollectionResponse> => {
  try {
    // Use axios directly without auth headers for public endpoint
    const response = await axios.get<PublicCollectionResponse>(
      `${API_BASE_URL}/share/${publicToken}`,
      { params: { limit, offset } },
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

// Public Request Sharing API

export interface MakeRequestPublicResponse {
  request_id: string;
  is_public: boolean;
  public_token: string | null;
  public_url: string | null;
  message: string;
}

export const makeRequestPublic = async (
  requestId: string,
): Promise<MakeRequestPublicResponse> => {
  try {
    const response = await api.post<MakeRequestPublicResponse>(
      `/logs/${requestId}/public`,
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

export const makeRequestPrivate = async (
  requestId: string,
): Promise<MakeRequestPublicResponse> => {
  try {
    const response = await api.delete<MakeRequestPublicResponse>(
      `/logs/${requestId}/public`,
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

export const getPublicRequest = async (
  publicToken: string,
): Promise<LogResponse> => {
  try {
    // Use axios directly without auth headers for public endpoint
    const response = await axios.get<LogResponse>(
      `${API_BASE_URL}/share/request/${publicToken}`,
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

/**
 * Get a request via a public collection's shareable token.
 * This allows accessing any request that belongs to a public collection,
 * even if the request itself is not individually marked as public.
 */
export const getRequestViaCollection = async (
  collectionToken: string,
  requestId: string,
): Promise<LogResponse> => {
  try {
    // Use axios directly without auth headers for public endpoint
    const response = await axios.get<LogResponse>(
      `${API_BASE_URL}/share/${collectionToken}/request/${requestId}`,
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

// ============================================================================
// Playground API
// ============================================================================

export type InjectionPosition =
  | "start"
  | "after_tokens"
  | "after_sentences"
  | "eot_backtrack"
  | "phrase_replace"
  | "reasoning_start"
  | "reasoning_mid"
  | "reasoning_end"
  | "response_start"
  | "response_mid"
  | "response_end"
  | "reasoning_phrase_replace"
  | "response_phrase_replace"
  | "full_stream_phrase_replace";

export interface ModConfig {
  injection_string: string;
  position: InjectionPosition;
  token_count?: number;
  sentence_count?: number;
  detect_phrases?: string[];
  replacement_phrases?: string[];
}

export interface PlaygroundKeyResponse {
  api_key: string;
  message: string;
}

export interface GenerateModResponse {
  code: string;
  mod_name: string;
}

export interface UploadModResponse {
  success: boolean;
  mod_name: string;
  message: string;
}

export interface ChatMessage {
  role: string;
  content: string;
}

export interface FeatureActivation {
  id: number;
  activation: number;
}

export interface FeatureTimelineEntry {
  position: number;
  token: number;
  token_str: string;
  top_features: FeatureActivation[];
}

export interface RunInferenceResponse {
  text: string;
  request_id: string | null;
  raw_response: Record<string, unknown>;
  feature_timeline?: FeatureTimelineEntry[];
}

export interface ExtractFeaturesRequest {
  model: string;
  tokens: number[];
  top_k?: number;
  layer?: number;
  injection_positions?: number[];
}

export interface ExtractFeaturesResponse {
  feature_timeline: FeatureTimelineEntry[];
  comparisons?: Array<{
    position: number;
    before?: FeatureTimelineEntry | FeatureTimelineEntry[];
    injection: FeatureTimelineEntry;
    after?: FeatureTimelineEntry | FeatureTimelineEntry[];
  }>;
}

export interface FeatureWithDescription {
  id: number;
  activation: number;
  description: string;
}

export interface AnalyzeFeaturesResponse {
  analysis: string;
  top_features: FeatureWithDescription[];
}

/**
 * Generate a temporary API key for playground use
 */
export const generatePlaygroundKey = async (
  sessionId?: string,
): Promise<PlaygroundKeyResponse> => {
  try {
    const response = await axios.post<PlaygroundKeyResponse>(
      `${API_BASE_URL}/playground/api-key`,
      { session_id: sessionId },
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

/**
 * Generate mod code from configuration
 */
export const generateModCode = async (
  config: ModConfig,
): Promise<GenerateModResponse> => {
  try {
    const response = await axios.post<GenerateModResponse>(
      `${API_BASE_URL}/playground/mods/generate`,
      { config },
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

/**
 * Upload a mod to a model server
 */
export const uploadMod = async (
  model: string,
  code: string,
  modName: string,
  apiKey: string,
): Promise<UploadModResponse> => {
  try {
    const response = await axios.post<UploadModResponse>(
      `${API_BASE_URL}/playground/mods/upload`,
      {
        model,
        code,
        mod_name: modName,
      },
      {
        headers: {
          "X-API-Key": apiKey,
        },
      },
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

/**
 * Run inference with optional mod
 */
export const runPlaygroundInference = async (
  model: string,
  messages: ChatMessage[],
  apiKey: string,
  modName?: string,
  maxTokens?: number,
  temperature?: number,
  extractFeatures?: boolean,
): Promise<RunInferenceResponse> => {
  try {
    const response = await axios.post<RunInferenceResponse>(
      `${API_BASE_URL}/playground/inference`,
      {
        model,
        messages,
        mod_name: modName,
        max_tokens: maxTokens,
        temperature,
        extract_features: extractFeatures,
      },
      {
        headers: {
          "X-API-Key": apiKey,
        },
      },
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

/**
 * Extract SAE features for a token sequence
 */
export const extractFeatures = async (
  model: string,
  tokens: number[],
  apiKey: string,
  options?: {
    top_k?: number;
    layer?: number;
    injection_positions?: number[];
  },
): Promise<ExtractFeaturesResponse> => {
  try {
    const response = await axios.post<ExtractFeaturesResponse>(
      `${API_BASE_URL}/playground/features/extract`,
      {
        model,
        tokens,
        ...options,
      },
      {
        headers: {
          "X-API-Key": apiKey,
        },
        timeout: 120000, // 2 minute timeout for feature extraction
      },
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

/**
 * Analyze SAE features using Claude
 */
export const analyzeFeatures = async (
  model: string,
  featureTimeline: FeatureTimelineEntry[],
  apiKey: string,
  options?: {
    injection_positions?: number[];
    context?: string;
    layer?: number;
  },
): Promise<AnalyzeFeaturesResponse> => {
  try {
    const response = await axios.post<AnalyzeFeaturesResponse>(
      `${API_BASE_URL}/playground/features/analyze`,
      {
        model,
        feature_timeline: featureTimeline,
        ...options,
      },
      {
        headers: {
          "X-API-Key": apiKey,
        },
        timeout: 120000, // 2 minute timeout for analysis
      },
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

// Activation Explorer APIs

export interface ActivationExplorerRunRequest {
  prompt: string;
  model_id?: string;
  max_tokens?: number;
  temperature?: number;
  top_p?: number;
  top_k?: number;
  collect_activations?: boolean;
  inline_sae?: boolean;
  sae_id?: string;
  sae_layer?: number;
  sae_top_k?: number;
  sae_local_path?: string;
  request_id?: string;
}

export interface ActivationExplorerRunSummary {
  request_id: string;
  created_at: string;
  model_id: string;
  prompt_chars: number;
  output_tokens: number;
  events_count: number;
  actions_count: number;
  activation_rows_count: number;
  unique_features_count: number;
  sae_enabled: boolean;
  sae_id?: string | null;
  sae_layer?: number | null;
  duration_ms: number;
  status: "ok" | "error";
  error_message?: string | null;
  top_features_preview?: unknown;
}

export interface ActivationExplorerRunResponse {
  request_id: string;
  status: "ok";
  run_summary: ActivationExplorerRunSummary;
  output: {
    text: string;
    token_ids: number[];
  };
  preview: {
    events: Record<string, unknown>[];
    actions: Record<string, unknown>[];
    activation_rows: Record<string, unknown>[];
  };
  created_at: string;
}

export interface ActivationExplorerRunsResponse {
  items: ActivationExplorerRunSummary[];
  next_cursor: string | null;
}

export interface ActivationExplorerRowsResponse {
  request_id: string;
  row_count: number;
  rows: Record<string, unknown>[];
}

export interface ActivationExplorerFeatureDeltasResponse {
  request_id: string;
  feature_id: number;
  rows: Record<string, unknown>[];
}

export interface ActivationExplorerTopFeaturesResponse {
  request_id: string;
  items: Record<string, unknown>[];
}

export interface ActivationExplorerHealthResponse {
  status: "ok" | "degraded";
  index_db_reachable: boolean;
  hf_inference_reachable: boolean;
  sae_reachable: boolean;
  last_error: string | null;
}

export const runActivationExplorer = async (
  payload: ActivationExplorerRunRequest,
): Promise<ActivationExplorerRunResponse> => {
  try {
    const response = await axios.post<ActivationExplorerRunResponse>(
      `${API_BASE_URL}/playground/activations/run`,
      payload,
      {
        timeout: 240000,
      },
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

export const listActivationExplorerRuns = async (params?: {
  limit?: number;
  cursor?: string;
  status?: "ok" | "error";
  model_id?: string;
  sae_enabled?: boolean;
}): Promise<ActivationExplorerRunsResponse> => {
  try {
    const response = await axios.get<ActivationExplorerRunsResponse>(
      `${API_BASE_URL}/playground/activations/runs`,
      { params },
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

export const getActivationExplorerRunSummary = async (
  requestId: string,
): Promise<ActivationExplorerRunSummary> => {
  try {
    const response = await axios.get<ActivationExplorerRunSummary>(
      `${API_BASE_URL}/playground/activations/${encodeURIComponent(requestId)}/summary`,
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

export const getActivationExplorerRows = async (
  requestId: string,
  params?: {
    feature_id?: number;
    sae_layer?: number;
    token_start?: number;
    token_end?: number;
    rank_max?: number;
    limit?: number;
  },
): Promise<ActivationExplorerRowsResponse> => {
  try {
    const response = await axios.get<ActivationExplorerRowsResponse>(
      `${API_BASE_URL}/playground/activations/${encodeURIComponent(requestId)}/rows`,
      { params },
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

export const getActivationExplorerFeatureDeltas = async (
  requestId: string,
  params: {
    feature_id: number;
    sae_layer?: number;
    limit?: number;
  },
): Promise<ActivationExplorerFeatureDeltasResponse> => {
  try {
    const response = await axios.get<ActivationExplorerFeatureDeltasResponse>(
      `${API_BASE_URL}/playground/activations/${encodeURIComponent(requestId)}/feature-deltas`,
      { params },
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

export const getActivationExplorerTopFeatures = async (
  requestId: string,
  params?: {
    n?: number;
    sae_layer?: number;
  },
): Promise<ActivationExplorerTopFeaturesResponse> => {
  try {
    const response = await axios.get<ActivationExplorerTopFeaturesResponse>(
      `${API_BASE_URL}/playground/activations/${encodeURIComponent(requestId)}/top-features`,
      { params },
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};

export const getActivationExplorerHealth = async (): Promise<ActivationExplorerHealthResponse> => {
  try {
    const response = await axios.get<ActivationExplorerHealthResponse>(
      `${API_BASE_URL}/playground/activations/health`,
    );
    return response.data;
  } catch (error) {
    return handleApiError(error);
  }
};
