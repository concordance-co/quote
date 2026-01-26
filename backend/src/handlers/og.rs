use axum::{
    extract::{Path, State},
    http::{header, HeaderMap, StatusCode},
    response::{Html, IntoResponse, Response},
    Json,
};

use crate::handlers::logs::{fetch_log_response, LogResponse};
use crate::utils::{ApiError, AppState};

/// Detect crawler user-agents that need OG meta tags
fn is_crawler(headers: &HeaderMap) -> bool {
    let ua = headers
        .get(header::USER_AGENT)
        .and_then(|v| v.to_str().ok())
        .unwrap_or("")
        .to_lowercase();

    [
        "twitterbot",
        "slackbot",
        "facebookexternalhit",
        "linkedinbot",
        "discordbot",
        "telegrambot",
        "whatsapp",
        "googlebot",
        "bingbot",
    ]
    .iter()
    .any(|bot| ua.contains(bot))
}

/// Escape HTML/XML special characters
fn html_escape(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&apos;")
}

/// Truncate string to max chars, adding ellipsis if needed
fn truncate(s: &str, max_chars: usize) -> String {
    if s.chars().count() > max_chars {
        format!("{}...", s.chars().take(max_chars.saturating_sub(3)).collect::<String>())
    } else {
        s.to_string()
    }
}

/// Extract short model name from full model path
fn short_model_name(model: &str) -> String {
    // Extract just the model name, e.g., "modularai/Llama-3.1-8B-Instruct-GGUF/playground_mod" -> "llama-3.1-8b"
    let lower = model.to_lowercase();
    if lower.contains("llama-3.1-8b") || lower.contains("llama-3.1-8") {
        "llama-3.1-8b".to_string()
    } else if lower.contains("llama") {
        "llama".to_string()
    } else if lower.contains("gpt-4") {
        "gpt-4".to_string()
    } else if lower.contains("gpt-3") {
        "gpt-3.5".to_string()
    } else if lower.contains("claude") {
        "claude".to_string()
    } else {
        // Take last path segment or first 15 chars
        model.split('/').last().unwrap_or(model).chars().take(15).collect()
    }
}

/// Extract injection info from log actions
fn extract_injection_info(log: &LogResponse) -> Option<InjectionInfo> {
    // Look for ForceTokens actions
    for action in &log.actions {
        if action.action_type == "ForceTokens" {
            // Extract tokens_as_text from payload
            if let Some(tokens_array) = action.payload.get("tokens_as_text").and_then(|v| v.as_array()) {
                let injection_string: String = tokens_array
                    .iter()
                    .filter_map(|v| v.as_str())
                    .collect();

                if !injection_string.is_empty() {
                    return Some(InjectionInfo {
                        injection_string,
                        position: "Start of Generation".to_string(), // Could be refined later
                    });
                }
            }
        }
    }
    None
}

/// Info about injected tokens
struct InjectionInfo {
    injection_string: String,
    position: String,
}

/// Generate SVG matching ShareableCard design for OG image
fn generate_og_svg(
    model: &str,
    max_tokens: Option<i32>,
    user_prompt: &str,
    system_prompt: Option<&str>,
    output_text: &str,
    share_url: &str,
    injection: Option<InjectionInfo>,
) -> String {
    let model_short = html_escape(&short_model_name(model));
    let tokens_str = max_tokens.map(|t| format!("{} tokens", t)).unwrap_or_else(|| "256 tokens".to_string());
    let user_prompt_escaped = html_escape(&truncate(user_prompt, 60));
    let system_escaped = html_escape(&truncate(system_prompt.unwrap_or("You are a helpful assistant."), 50));
    let url_display = html_escape(&truncate(share_url, 50));

    // Build injection section if present
    let injection_section = if let Some(ref inj) = injection {
        let inj_str = html_escape(&truncate(&inj.injection_string, 30));
        let pos = html_escape(&inj.position);
        format!(
            r##"
  <!-- INJECTION section -->
  <text x="40" y="268" fill="#34d399" font-size="16" font-weight="bold" font-family="IBM Plex Mono">⚡ INJECTION</text>
  <text x="40" y="295" fill="#737373" font-size="14" font-family="IBM Plex Mono">POSITION: <tspan fill="#34d399">{pos}</tspan>    STRING: <tspan fill="#34d399">"{inj_str}"</tspan></text>
"##,
            pos = pos,
            inj_str = inj_str
        )
    } else {
        String::new()
    };

    // Adjust output Y position based on whether injection section exists
    let output_y_start = if injection.is_some() { 340 } else { 280 };

    // Build output with highlighting if injection present
    let output_section = build_output_section(output_text, output_y_start, injection.as_ref());

    // Footer badge
    let footer_badge = if injection.is_some() {
        r##"<circle cx="1050" cy="590" r="6" fill="#ec4899"/>
  <text x="1065" y="595" fill="#a3a3a3" font-size="14" font-family="IBM Plex Mono">injected</text>"##
    } else {
        ""
    };

    format!(
        r##"<svg width="1200" height="628" xmlns="http://www.w3.org/2000/svg">
  <!-- Background -->
  <rect width="1200" height="628" fill="#0d0d0d"/>

  <!-- Header -->
  <polygon points="40,22 55,44 25,44" fill="#34d399"/>
  <text x="70" y="42" fill="#ffffff" font-size="22" font-weight="bold" font-family="IBM Plex Mono">TOKEN INJECTION LAB</text>
  <text x="1160" y="42" fill="#737373" font-size="18" text-anchor="end" font-family="IBM Plex Mono">Concordance.co</text>

  <!-- Model badges row -->
  <rect x="40" y="70" width="160" height="36" rx="6" fill="transparent" stroke="#34d399" stroke-width="1.5"/>
  <text x="120" y="95" fill="#34d399" font-size="16" text-anchor="middle" font-family="IBM Plex Mono">{model}</text>

  <circle cx="220" cy="88" r="3" fill="#525252"/>

  <rect x="240" y="70" width="130" height="36" rx="6" fill="#1a1a1a"/>
  <text x="305" y="95" fill="#a3a3a3" font-size="15" text-anchor="middle" font-family="IBM Plex Mono">{tokens}</text>

  <!-- USER section -->
  <text x="40" y="150" fill="#737373" font-size="14" font-family="IBM Plex Mono">USER</text>
  <text x="40" y="178" fill="#ffffff" font-size="20" font-family="IBM Plex Mono">{user_prompt}</text>

  <!-- SYSTEM section -->
  <text x="700" y="150" fill="#737373" font-size="14" font-family="IBM Plex Mono">SYSTEM</text>
  <text x="700" y="178" fill="#a3a3a3" font-size="18" font-family="IBM Plex Mono">{system}</text>

  <!-- Divider line -->
  <line x1="40" y1="210" x2="1160" y2="210" stroke="#262626" stroke-width="1"/>
{injection_section}
  <!-- OUTPUT section -->
  <text x="40" y="{output_label_y}" fill="#737373" font-size="14" font-family="IBM Plex Mono">OUTPUT</text>
{output_section}

  <!-- Footer -->
  <line x1="40" y1="560" x2="1160" y2="560" stroke="#262626" stroke-width="1"/>
  <text x="40" y="595" fill="#34d399" font-size="16" font-family="IBM Plex Mono">{url}</text>
  {footer_badge}
</svg>"##,
        model = model_short,
        tokens = tokens_str,
        user_prompt = user_prompt_escaped,
        system = system_escaped,
        injection_section = injection_section,
        output_label_y = output_y_start - 15,
        output_section = output_section,
        url = url_display,
        footer_badge = footer_badge,
    )
}

/// Build output section with optional injection highlighting
fn build_output_section(output_text: &str, y_start: i32, injection: Option<&InjectionInfo>) -> String {
    let line_height = 32;
    let max_chars_per_line = 85;
    let max_lines = 4;

    // Wrap text into lines
    let mut lines: Vec<String> = Vec::new();
    let mut current_line = String::new();

    for word in output_text.split_whitespace() {
        if current_line.is_empty() {
            current_line = word.to_string();
        } else if current_line.len() + 1 + word.len() <= max_chars_per_line {
            current_line.push(' ');
            current_line.push_str(word);
        } else {
            lines.push(current_line);
            current_line = word.to_string();
            if lines.len() >= max_lines {
                break;
            }
        }
    }
    if !current_line.is_empty() && lines.len() < max_lines {
        lines.push(current_line);
    }

    // Add ellipsis to last line if we truncated
    if lines.len() == max_lines && output_text.split_whitespace().count() > lines.iter().map(|l| l.split_whitespace().count()).sum::<usize>() {
        if let Some(last) = lines.last_mut() {
            if last.len() > max_chars_per_line - 3 {
                *last = last.chars().take(max_chars_per_line - 3).collect();
            }
            last.push_str("...");
        }
    }

    let mut svg_lines = String::new();

    for (i, line) in lines.iter().enumerate() {
        let y = y_start + (i as i32 * line_height);

        // Check if this line contains the injection string
        if let Some(inj) = injection {
            if let Some(pos) = line.find(&inj.injection_string) {
                // Split into before, highlighted, after
                let before = html_escape(&line[..pos]);
                let highlighted = html_escape(&inj.injection_string);
                let after = html_escape(&line[pos + inj.injection_string.len()..]);

                // Calculate positions (approximate: 11px per char for IBM Plex Mono at 18px)
                let char_width = 11;
                let before_width = before.chars().count() as i32 * char_width;
                let highlight_width = highlighted.chars().count() as i32 * char_width + 12;

                svg_lines.push_str(&format!(
                    r##"  <text x="40" y="{y}" fill="#e5e5e5" font-size="18" font-family="IBM Plex Mono">{before}</text>
  <rect x="{hx}" y="{hy}" width="{hw}" height="26" rx="4" fill="#be185d"/>
  <text x="{htx}" y="{y}" fill="#ffffff" font-size="18" font-family="IBM Plex Mono">{highlighted}</text>
  <text x="{ax}" y="{y}" fill="#e5e5e5" font-size="18" font-family="IBM Plex Mono">{after}</text>
"##,
                    y = y,
                    before = before,
                    hx = 40 + before_width - 2,
                    hy = y - 19,
                    hw = highlight_width,
                    htx = 40 + before_width + 4,
                    highlighted = highlighted,
                    ax = 40 + before_width + highlight_width + 2,
                    after = after,
                ));
                continue;
            }
        }

        // Regular line without highlighting
        svg_lines.push_str(&format!(
            r##"  <text x="40" y="{}" fill="#e5e5e5" font-size="18" font-family="IBM Plex Mono">{}</text>
"##,
            y,
            html_escape(line)
        ));
    }

    svg_lines
}

/// Generate and serve OG image as PNG
///
/// GET /share/request/{token}/og-image.png
pub async fn og_image_handler(
    State(state): State<AppState>,
    Path(public_token): Path<String>,
) -> Result<Response, ApiError> {
    // Fetch request data
    let request_id: Option<String> = sqlx::query_scalar(
        "SELECT request_id FROM requests WHERE public_token = $1 AND is_public = TRUE",
    )
    .bind(&public_token)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    let request_id =
        request_id.ok_or_else(|| ApiError::NotFound("Public request not found".into()))?;

    let log = fetch_log_response(&state.db_pool, &request_id).await?;

    let share_url = format!("concordance.co/share/request/{}", public_token);

    // Extract injection info from ForceTokens actions
    let injection = extract_injection_info(&log);

    // Generate SVG
    let svg = generate_og_svg(
        log.model_id.as_deref().unwrap_or("unknown"),
        log.max_steps,
        log.user_prompt.as_deref().unwrap_or(""),
        log.system_prompt.as_deref(),
        log.final_text.as_deref().unwrap_or(""),
        &share_url,
        injection,
    );

    // Convert SVG to PNG using resvg
    let mut fontdb = fontdb::Database::new();

    // Load IBM Plex Mono fonts (embedded in binary)
    static IBM_PLEX_MONO_REGULAR: &[u8] = include_bytes!("../../assets/fonts/IBMPlexMono-Regular.ttf");
    static IBM_PLEX_MONO_MEDIUM: &[u8] = include_bytes!("../../assets/fonts/IBMPlexMono-Medium.ttf");
    static IBM_PLEX_MONO_SEMIBOLD: &[u8] = include_bytes!("../../assets/fonts/IBMPlexMono-SemiBold.ttf");

    fontdb.load_font_data(IBM_PLEX_MONO_REGULAR.to_vec());
    fontdb.load_font_data(IBM_PLEX_MONO_MEDIUM.to_vec());
    fontdb.load_font_data(IBM_PLEX_MONO_SEMIBOLD.to_vec());

    let mut options = usvg::Options::default();
    options.fontdb = std::sync::Arc::new(fontdb);

    let tree = usvg::Tree::from_str(&svg, &options)
        .map_err(|e| ApiError::internal(format!("Failed to parse SVG: {}", e)))?;

    let pixmap_size = tree.size().to_int_size();
    let mut pixmap = tiny_skia::Pixmap::new(pixmap_size.width(), pixmap_size.height())
        .ok_or_else(|| ApiError::internal("Failed to create pixmap".to_string()))?;

    resvg::render(&tree, tiny_skia::Transform::default(), &mut pixmap.as_mut());

    let png_data = pixmap
        .encode_png()
        .map_err(|e| ApiError::internal(format!("Failed to encode PNG: {}", e)))?;

    Ok((
        StatusCode::OK,
        [
            (header::CONTENT_TYPE, "image/png"),
            (header::CACHE_CONTROL, "public, max-age=3600"),
        ],
        png_data,
    )
        .into_response())
}

/// Serve HTML with OG tags for crawlers, JSON for regular browsers
///
/// GET /share/request/{token}
pub async fn share_request_with_og(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(public_token): Path<String>,
) -> Result<Response, ApiError> {
    if !is_crawler(&headers) {
        // Regular browsers get JSON (existing behavior)
        let response = get_public_request_json(State(state), Path(public_token)).await?;
        return Ok(response.into_response());
    }

    // Crawlers get HTML with OG meta tags
    let request_id: Option<String> = sqlx::query_scalar(
        "SELECT request_id FROM requests WHERE public_token = $1 AND is_public = TRUE",
    )
    .bind(&public_token)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    let request_id =
        request_id.ok_or_else(|| ApiError::NotFound("Public request not found".into()))?;

    let log = fetch_log_response(&state.db_pool, &request_id).await?;

    let title = format!(
        "Inference Log - {}",
        log.model_id.as_deref().unwrap_or("Concordance")
    );
    let description = log
        .user_prompt
        .as_deref()
        .unwrap_or("View this inference log on Concordance");
    let image_url = format!(
        "https://concordance.co/share/request/{}/og-image.png",
        public_token
    );
    let page_url = format!("https://concordance.co/share/request/{}", public_token);

    let html = format!(
        r#"<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{description}">
  <meta property="og:image" content="{image_url}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="628">
  <meta property="og:type" content="website">
  <meta property="og:url" content="{page_url}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{title}">
  <meta name="twitter:description" content="{description}">
  <meta name="twitter:image" content="{image_url}">
  <meta http-equiv="refresh" content="0;url={page_url}">
  <script>window.location.href = "{page_url}";</script>
  <title>{title}</title>
</head>
<body>Loading...</body>
</html>"#,
        title = html_escape(&title),
        description = html_escape(description),
        image_url = image_url,
        page_url = page_url
    );

    Ok(Html(html).into_response())
}

/// Internal helper to get public request as JSON (used by share_request_with_og)
async fn get_public_request_json(
    State(state): State<AppState>,
    Path(public_token): Path<String>,
) -> Result<Json<LogResponse>, ApiError> {
    // Find the request by public token
    let request_id: Option<String> = sqlx::query_scalar(
        "SELECT request_id FROM requests WHERE public_token = $1 AND is_public = TRUE",
    )
    .bind(&public_token)
    .fetch_optional(&state.db_pool)
    .await
    .map_err(ApiError::from)?;

    let request_id = request_id
        .ok_or_else(|| ApiError::NotFound("Public request not found or link has expired".into()))?;

    // Check cache first
    if let Some(cached) = state.log_cache.get(&request_id) {
        tracing::debug!(request_id = %request_id, "Public request cache hit");
        let mut response = cached;
        // Never expose user_api_key in public endpoints
        response.user_api_key = None;
        return Ok(Json(response));
    }

    tracing::debug!(request_id = %request_id, "Public request cache miss");

    // Fetch the full log response
    let response = fetch_log_response(&state.db_pool, &request_id).await?;

    // Cache the response for future requests
    state.log_cache.insert(request_id, response.clone());

    // Never expose user_api_key in public endpoints
    let mut response = response;
    response.user_api_key = None;

    Ok(Json(response))
}
