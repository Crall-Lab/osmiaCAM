#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(dplyr)
  library(ggplot2)
  library(lubridate)
  library(mgcv)
  library(purrr)
  library(readr)
  library(stringr)
  library(tidyr)
})

`%||%` <- function(a, b) {
  if (!is.null(a)) a else b
}

roi_letter_map <- c(`2` = "K", `3` = "L", `4` = "M", `5` = "N", `6` = "O", `7` = "P", `8` = "Q")
roi_levels <- unname(roi_letter_map)
roi_palette <- c(
  K = "#1b9e77",
  L = "#d95f02",
  M = "#7570b3",
  N = "#e7298a",
  O = "#66a61e",
  P = "#e6ab02",
  Q = "#a6761d"
)
roi_cells_provisioned <- c(
  K = 0L,
  L = 2L,
  M = 2L,
  N = 2L,
  O = 4L,
  P = 4L,
  Q = 0L
)

save_plot_dual <- function(p, out_dir, stem, width, height, dpi = 300) {
  ggsave(file.path(out_dir, paste0(stem, ".png")), p, width = width, height = height, dpi = dpi)
  ggsave(file.path(out_dir, paste0(stem, ".pdf")), p, width = width, height = height, device = "pdf")
}

parse_cli_args <- function() {
  args <- commandArgs(trailingOnly = TRUE)
  out <- list(
    base_dir = "extCam_clean",
    run_tag = "roi_trial_full_v1_with_video",
    output_dir = NULL,
    unit = "osmia4",
    tz = "America/Los_Angeles",
    weather_dirs = NULL
  )
  i <- 1
  while (i <= length(args)) {
    key <- args[[i]]
    val <- if (i < length(args)) args[[i + 1]] else NA_character_
    if (key == "--base-dir") out$base_dir <- val
    if (key == "--run-tag") out$run_tag <- val
    if (key == "--output-dir") out$output_dir <- val
    if (key == "--unit") out$unit <- val
    if (key == "--tz") out$tz <- val
    if (key == "--weather-dirs") out$weather_dirs <- str_split(val, ",", simplify = TRUE) %>% as.character()
    i <- i + 2
  }
  out
}

normalize_unit <- function(x) {
  x_norm <- tolower(trimws(x))
  x_norm <- gsub("[^a-z0-9]", "", x_norm)
  case_when(
    x_norm %in% c("osmia4", "osmia04") ~ "osmia4",
    x_norm %in% c("osmia3", "osmia03") ~ "osmia3",
    x_norm %in% c("jimsranch") ~ "megachilidae",
    TRUE ~ x_norm
  )
}

parse_video_start <- function(video_name, tz_name) {
  mm <- str_match(video_name, "^([^_]+)_(\\d{4}-\\d{2}-\\d{2})_(\\d{2}-\\d{2}-\\d{2})_")
  tibble(
    video = video_name,
    unit_raw = mm[, 2],
    unit = normalize_unit(mm[, 2]),
    video_date = mm[, 3],
    video_time = mm[, 4],
    video_start = ymd_hms(
      paste(mm[, 3], str_replace_all(mm[, 4], "-", ":")),
      tz = tz_name,
      quiet = TRUE
    )
  )
}

continuous_doy <- function(dt) {
  yday(dt) + (hour(dt) + minute(dt) / 60 + second(dt) / 3600) / 24
}

load_all_events <- function(base_dir, run_tag, tz_name) {
  files_all <- list.files(base_dir, pattern = "events\\.csv$", recursive = TRUE, full.names = TRUE)
  files <- files_all[grepl(paste0("/analysis_output/", run_tag, "/events\\.csv$"), files_all)]
  if (length(files) == 0) {
    stop("No events.csv files found under run_tag: ", run_tag)
  }
  message("Found ", length(files), " events.csv files")

  events <- map_dfr(files, function(f) {
    x <- read_csv(f, show_col_types = FALSE, progress = FALSE)
    if (nrow(x) == 0) return(tibble())
    day_folder <- basename(dirname(dirname(dirname(f))))
    x %>%
      mutate(
        source_events_file = f,
        source_day = day_folder
      )
  })

  if (nrow(events) == 0) stop("All events files were empty.")

  video_meta <- events %>%
    distinct(video) %>%
    mutate(video = as.character(video)) %>%
    group_split(video) %>%
    map_dfr(~ parse_video_start(.x$video[[1]], tz_name = tz_name))

  events2 <- events %>%
    mutate(
      video = as.character(video),
      direction = tolower(as.character(direction)),
      time_s = suppressWarnings(as.numeric(time_s)),
      start_frame = suppressWarnings(as.integer(start_frame)),
      end_frame = suppressWarnings(as.integer(end_frame))
    ) %>%
    left_join(video_meta, by = "video") %>%
    mutate(
      event_datetime = video_start + seconds(coalesce(time_s, 0)),
      day_of_year_cont = continuous_doy(event_datetime),
      roi_num = suppressWarnings(as.integer(str_extract(coalesce(roi_id, roi_name), "\\d+"))),
      transit_io = case_when(
        direction == "up" ~ "in",
        direction == "down" ~ "out",
        TRUE ~ NA_character_
      )
    )

  events2
}

read_envlog_file <- function(f, tz_name) {
  x <- read_csv(
    f,
    col_names = c("datetime", "outer_pressure", "outer_temp", "outer_hum", "inner_temp", "inner_hum"),
    show_col_types = FALSE,
    progress = FALSE
  )
  unit_raw <- str_split_fixed(basename(f), "_", n = 2)[, 1]
  x %>%
    mutate(
      source_file = f,
      sensor_source = "envlog",
      unit_raw = unit_raw,
      unit = normalize_unit(unit_raw),
      datetime_parsed = parse_date_time(
        datetime,
        orders = c("ymd_HMS", "ymd HMS", "ymd HM", "mdy HM", "mdy HMS"),
        tz = tz_name,
        quiet = TRUE
      ),
      outer_temp_c = suppressWarnings(as.numeric(outer_temp))
    ) %>%
    select(unit, datetime_parsed, outer_temp_c, sensor_source, source_file)
}

read_govee_file <- function(f, tz_name) {
  raw <- read_csv(f, col_names = FALSE, show_col_types = FALSE, progress = FALSE)
  if (ncol(raw) < 2) return(tibble())
  x <- tibble(
    datetime = as.character(raw[[1]]),
    outer_temp_raw = suppressWarnings(as.numeric(raw[[2]])),
    outer_hum = if (ncol(raw) >= 3) suppressWarnings(as.numeric(raw[[3]])) else NA_real_
  )
  unit_raw <- str_split_fixed(basename(f), "_", n = 2)[, 1]
  unit_norm <- normalize_unit(unit_raw)
  temp_med <- suppressWarnings(median(x$outer_temp_raw, na.rm = TRUE))
  looks_f <- is.finite(temp_med) && temp_med > 45
  temp_c <- if (looks_f) (x$outer_temp_raw - 32) * (5 / 9) else x$outer_temp_raw

  x %>%
    mutate(
      source_file = f,
      sensor_source = "govee",
      unit_raw = unit_raw,
      unit = unit_norm,
      datetime_parsed = parse_date_time(
        datetime,
        orders = c("ymd_HMS", "ymd HMS", "ymd HM", "mdy HM", "mdy HMS"),
        tz = tz_name,
        quiet = TRUE
      ),
      outer_temp_c = temp_c
    ) %>%
    select(unit, datetime_parsed, outer_temp_c, sensor_source, source_file)
}

load_weather_data <- function(weather_dirs, tz_name, unit_focus = "osmia4") {
  weather_dirs <- unique(weather_dirs[dir.exists(weather_dirs)])
  if (length(weather_dirs) == 0) {
    message("No weather directories exist; skipping weather integration.")
    return(tibble())
  }

  env_files <- unlist(map(weather_dirs, ~ list.files(.x, pattern = "_envLog\\.csv$", recursive = TRUE, full.names = TRUE)))
  govee_files <- unlist(map(weather_dirs, ~ list.files(.x, pattern = "_govee\\.csv$", recursive = TRUE, full.names = TRUE)))

  message("Weather scan: ", length(env_files), " envLog files, ", length(govee_files), " govee files")
  if ((length(env_files) + length(govee_files)) == 0) return(tibble())

  env_df <- if (length(env_files) > 0) map_dfr(env_files, read_envlog_file, tz_name = tz_name) else tibble()
  govee_df <- if (length(govee_files) > 0) map_dfr(govee_files, read_govee_file, tz_name = tz_name) else tibble()

  bind_rows(env_df, govee_df) %>%
    filter(
      !is.na(datetime_parsed),
      !is.na(outer_temp_c),
      unit == normalize_unit(unit_focus)
    ) %>%
    mutate(day_of_year_cont = continuous_doy(datetime_parsed))
}

make_event_scatter_plot <- function(events_io, weather_df, out_dir) {
  xlim_rng <- c(109, 115)
  events_plot_df <- events_io %>%
    filter(day_of_year_cont >= xlim_rng[1], day_of_year_cont <= xlim_rng[2])

  events_2h_total <- events_io %>%
    mutate(bin_2h = floor_date(event_datetime, unit = "2 hours")) %>%
    count(bin_2h, name = "total_transits_2h") %>%
    mutate(day_of_year_cont = continuous_doy(bin_2h)) %>%
    filter(day_of_year_cont >= xlim_rng[1], day_of_year_cont <= xlim_rng[2])

  weather_raw_df <- weather_df %>%
    mutate(day_of_year_cont = continuous_doy(datetime_parsed)) %>%
    filter(day_of_year_cont >= xlim_rng[1], day_of_year_cont <= xlim_rng[2])

  p_events <- ggplot(events_plot_df, aes(x = day_of_year_cont, y = roi_label, color = transit_io)) +
    geom_point(alpha = 0.7, size = 1.5) +
    scale_color_manual(values = c("in" = "#f4a3a3", "out" = "#006400"), drop = FALSE) +
    scale_y_discrete(limits = roi_levels, drop = FALSE) +
    scale_x_continuous(limits = xlim_rng) +
    labs(
      title = "Osmia4 Transit Events Across Time",
      x = "Day of year (continuous)",
      y = "ROI",
      color = "Transit"
    ) +
    theme_minimal(base_size = 12)

  if (!requireNamespace("patchwork", quietly = TRUE)) {
    save_plot_dual(p_events, out_dir = out_dir, stem = "osmia4_events_time_vs_roi_in_out", width = 12, height = 4.5)
    return(p_events)
  }

  p_total <- ggplot(events_2h_total, aes(x = day_of_year_cont, y = total_transits_2h)) +
    geom_col(fill = "#2b6cb0", alpha = 0.45, width = 0.07) +
    geom_line(color = "#1f4e79", linewidth = 0.45) +
    geom_point(color = "#1f4e79", size = 0.8) +
    scale_x_continuous(limits = xlim_rng) +
    labs(
      x = "Day of year (continuous)",
      y = "Total transits\n(2-hour blocks)"
    ) +
    theme_minimal(base_size = 11)

  p_temp <- ggplot(weather_raw_df, aes(x = day_of_year_cont, y = outer_temp_c)) +
    geom_line(color = "grey45", linewidth = 0.35, alpha = 0.65) +
    geom_point(color = "grey30", size = 0.45, alpha = 0.35) +
    scale_x_continuous(limits = xlim_rng) +
    labs(
      x = "Day of year (continuous)",
      y = "Ambient temp\n(raw, C)"
    ) +
    theme_minimal(base_size = 11)

  strip_x <- theme(
    axis.title.x = element_blank(),
    axis.text.x = element_blank(),
    axis.ticks.x = element_blank()
  )
  p_events_nox <- p_events + strip_x
  p_total_nox <- p_total + strip_x

  p_combo <- p_events_nox / p_total_nox / p_temp + patchwork::plot_layout(heights = c(2.8, 1.2, 1.3))
  save_plot_dual(p_combo, out_dir = out_dir, stem = "osmia4_events_time_vs_roi_in_out", width = 12, height = 7.7)
  p_combo
}

make_two_hour_summary <- function(events_io, weather_df) {
  events_2h_raw <- events_io %>%
    mutate(bin_2h = floor_date(event_datetime, unit = "2 hours")) %>%
    group_by(roi_id, roi_num, roi_label, bin_2h) %>%
    summarise(
      transit_count = n(),
      in_count = sum(transit_io == "in", na.rm = TRUE),
      out_count = sum(transit_io == "out", na.rm = TRUE),
      .groups = "drop"
    )

  roi_meta <- events_io %>%
    distinct(roi_id, roi_num, roi_label)
  bin_seq <- seq(
    floor_date(min(events_io$event_datetime, na.rm = TRUE), unit = "2 hours"),
    floor_date(max(events_io$event_datetime, na.rm = TRUE), unit = "2 hours"),
    by = "2 hours"
  )

  events_2h <- tidyr::crossing(roi_meta, bin_2h = bin_seq) %>%
    left_join(events_2h_raw, by = c("roi_id", "roi_num", "roi_label", "bin_2h")) %>%
    mutate(
      transit_count = replace_na(transit_count, 0L),
      in_count = replace_na(in_count, 0L),
      out_count = replace_na(out_count, 0L)
    )

  if (nrow(weather_df) == 0) {
    return(events_2h %>%
      mutate(
        mean_temp_c = NA_real_,
        temp_n = NA_integer_,
        bin_day_of_year_cont = continuous_doy(bin_2h),
        cells_provisioned = as.integer(unname(roi_cells_provisioned[as.character(roi_label)]))
      ))
  }

  weather_2h <- weather_df %>%
    mutate(bin_2h = floor_date(datetime_parsed, unit = "2 hours")) %>%
    group_by(bin_2h) %>%
    summarise(
      mean_temp_c = mean(outer_temp_c, na.rm = TRUE),
      temp_n = n(),
      .groups = "drop"
    )

  events_2h %>%
    left_join(weather_2h, by = "bin_2h") %>%
    mutate(
      bin_day_of_year_cont = continuous_doy(bin_2h),
      cells_provisioned = as.integer(unname(roi_cells_provisioned[as.character(roi_label)]))
    )
}

make_weather_plots <- function(two_hour_df, out_dir, tz_name = "America/Los_Angeles") {
  if (nrow(two_hour_df) == 0) return(invisible(NULL))

  df_all <- two_hour_df %>%
    mutate(roi_label = factor(roi_label, levels = roi_levels))

  df_temp <- df_all %>% filter(!is.na(mean_temp_c))
  if (nrow(df_temp) > 0) {
    p1 <- ggplot(df_temp, aes(x = mean_temp_c, y = transit_count, color = roi_label)) +
      geom_point(alpha = 0.65, size = 1.7) +
      geom_smooth(
        aes(group = roi_label, color = roi_label),
        se = FALSE,
        method = "loess",
        formula = y ~ x,
        linewidth = 0.7
      ) +
      geom_smooth(
        data = df_temp,
        aes(x = mean_temp_c, y = transit_count),
        inherit.aes = FALSE,
        se = FALSE,
        method = "loess",
        formula = y ~ x,
        linewidth = 1.0,
        color = "black"
      ) +
      scale_color_manual(values = roi_palette, drop = FALSE) +
      labs(
        title = "Two-Hour Transit Count vs Mean Temperature (osmia4)",
        x = "Mean temperature in 2-hour block (°C)",
        y = "Transit count in 2-hour block",
        color = "ROI"
      ) +
      theme_minimal(base_size = 12)
    save_plot_dual(p1, out_dir = out_dir, stem = "osmia4_transits_vs_temp_2h", width = 9, height = 5)
  }

  p2 <- ggplot(df_all, aes(x = bin_day_of_year_cont, y = transit_count, color = roi_label)) +
    geom_rect(
      data = {
        min_day <- floor_date(min(df_all$bin_2h, na.rm = TRUE), unit = "day")
        max_day <- ceiling_date(max(df_all$bin_2h, na.rm = TRUE), unit = "day")
        day_seq <- seq(min_day, max_day, by = "1 day")
        tibble(
          xmin = continuous_doy(day_seq + hours(19)),
          xmax = continuous_doy(day_seq + lubridate::days(1) + hours(7))
        )
      },
      aes(xmin = xmin, xmax = xmax, ymin = -Inf, ymax = Inf),
      inherit.aes = FALSE,
      fill = "grey35",
      alpha = 0.18
    ) +
    geom_point(alpha = 0.75, size = 1.15) +
    scale_color_manual(values = roi_palette, drop = FALSE) +
    facet_wrap(~ roi_label, scales = "fixed") +
    scale_y_continuous(breaks = c(0, 10, 20, 30)) +
    coord_cartesian(ylim = c(0, 30)) +
    labs(
      title = "Two-Hour Transit Counts Through Time by ROI (osmia4)",
      x = "Day of year (continuous)",
      y = "Transit count per 2-hour block",
      color = "ROI"
    ) +
    theme_minimal(base_size = 11)
  save_plot_dual(p2, out_dir = out_dir, stem = "osmia4_transits_by_time_2h_by_roi", width = 12, height = 8)

  df_violin <- df_all %>%
    mutate(hour_local = hour(with_tz(bin_2h, tzone = tz_name))) %>%
    filter(hour_local >= 8, hour_local < 18)

  roi_order <- df_violin %>%
    group_by(roi_label) %>%
    summarise(mu = mean(transit_count, na.rm = TRUE), .groups = "drop") %>%
    arrange(mu) %>%
    pull(roi_label) %>%
    as.character()

  df_violin <- df_violin %>%
    mutate(roi_label_ordered = factor(as.character(roi_label), levels = roi_order))

  p3 <- ggplot(df_violin, aes(x = roi_label_ordered, y = transit_count + 1, color = roi_label_ordered, fill = roi_label_ordered)) +
    geom_violin(alpha = 0.28, trim = FALSE, linewidth = 0.3) +
    geom_jitter(width = 0.12, height = 0, alpha = 0.6, size = 1.0) +
    stat_summary(fun = mean, geom = "point", shape = 15, color = "black", size = 2.3) +
    scale_color_manual(values = roi_palette, guide = "none") +
    scale_fill_manual(values = roi_palette, guide = "none") +
    scale_y_log10() +
    labs(
      title = "Transit Counts per 2-Hour Block by ROI (osmia4)",
      subtitle = "Daylight bins only (08:00-18:00 local); ROIs ordered by mean transit count",
      x = "ROI",
      y = "Transits per 2-hour block (+1, log10 scale)"
    ) +
    theme_minimal(base_size = 12)
  save_plot_dual(p3, out_dir = out_dir, stem = "osmia4_transits_2h_violin_by_roi", width = 9, height = 5)
}

make_foraging_cells_relationship <- function(two_hour_df, out_dir, tz_name = "America/Los_Angeles") {
  if (nrow(two_hour_df) == 0) return(invisible(NULL))

  daylight_df <- two_hour_df %>%
    mutate(hour_local = hour(with_tz(bin_2h, tzone = tz_name))) %>%
    filter(hour_local >= 8, hour_local < 18)

  summary_source <- daylight_df
  if (nrow(summary_source) == 0) {
    message("No daylight 2-hour bins found; using all bins for foraging/cell relationship.")
    summary_source <- two_hour_df
  }

  nest_summary <- summary_source %>%
    mutate(roi_label = as.character(roi_label)) %>%
    group_by(roi_label, cells_provisioned) %>%
    summarise(
      mean_foraging_2h = mean(transit_count, na.rm = TRUE),
      median_foraging_2h = median(transit_count, na.rm = TRUE),
      total_foraging = sum(transit_count, na.rm = TRUE),
      n_bins = n(),
      .groups = "drop"
    ) %>%
    mutate(roi_label = factor(roi_label, levels = roi_levels)) %>%
    arrange(roi_label)

  if (nrow(nest_summary) == 0) return(invisible(NULL))

  fit <- lm(cells_provisioned ~ mean_foraging_2h, data = nest_summary)
  fit_r2 <- summary(fit)$r.squared

  p_rel <- ggplot(
    nest_summary,
    aes(x = mean_foraging_2h, y = cells_provisioned, color = roi_label)
  ) +
    geom_point(size = 3) +
    geom_text(aes(label = roi_label), nudge_y = 0.15, show.legend = FALSE) +
    geom_smooth(
      method = "lm",
      formula = y ~ x,
      se = FALSE,
      linewidth = 0.8,
      color = "black"
    ) +
    scale_color_manual(values = roi_palette, drop = FALSE) +
    labs(
      title = "Nest Provisioning vs Mean Foraging Activity (2-hour bins)",
      subtitle = paste0("R^2 = ", format(round(fit_r2, 3), nsmall = 3)),
      x = "Mean transit count per 2-hour block (daylight bins)",
      y = "Cells provisioned",
      color = "Nest"
    ) +
    theme_minimal(base_size = 12)

  save_plot_dual(
    p_rel,
    out_dir = out_dir,
    stem = "osmia4_cells_vs_mean_foraging_2h",
    width = 7.5,
    height = 5
  )

  list(summary = nest_summary, model = fit)
}

make_validation_summary <- function(events_all, events_io, two_hour_df, tz_name = "America/Los_Angeles") {
  day_bins <- two_hour_df %>%
    mutate(hour_local = hour(with_tz(bin_2h, tzone = tz_name))) %>%
    filter(hour_local >= 8, hour_local < 18)

  tibble(
    metric = c(
      "total_videos_tracked",
      "total_foraging_transits_inferred",
      "total_raw_event_rows",
      "roi_nests_analyzed",
      "two_hour_bins_total",
      "two_hour_bins_daylight"
    ),
    value = c(
      n_distinct(events_all$video),
      nrow(events_io),
      nrow(events_all),
      n_distinct(events_io$roi_label),
      n_distinct(two_hour_df$bin_2h),
      n_distinct(day_bins$bin_2h)
    )
  )
}

run_nest_block_nonparametric_test <- function(two_hour_df, tz_name = "America/Los_Angeles") {
  df_kw <- two_hour_df %>%
    mutate(
      roi_label = factor(roi_label, levels = roi_levels),
      hour_local = hour(with_tz(bin_2h, tzone = tz_name))
    ) %>%
    filter(hour_local >= 8, hour_local < 18) %>%
    filter(!is.na(roi_label), !is.na(transit_count))

  if (nrow(df_kw) == 0) {
    return(NULL)
  }

  kw <- kruskal.test(transit_count ~ roi_label, data = df_kw)
  kw_summary <- tibble(
    test = "kruskal_wallis_transits_by_nest",
    statistic = as.numeric(kw$statistic),
    df = as.integer(kw$parameter),
    p_value = as.numeric(kw$p.value),
    n_observations = nrow(df_kw),
    n_nests = n_distinct(df_kw$roi_label)
  )

  pw <- pairwise.wilcox.test(
    x = df_kw$transit_count,
    g = df_kw$roi_label,
    p.adjust.method = "BH",
    exact = FALSE
  )
  pw_tbl <- as.data.frame(as.table(pw$p.value), stringsAsFactors = FALSE) %>%
    as_tibble() %>%
    rename(nest_1 = Var1, nest_2 = Var2, p_value_bh = Freq) %>%
    filter(!is.na(p_value_bh))

  list(
    kruskal_summary = kw_summary,
    pairwise_wilcox = pw_tbl
  )
}

run_temperature_gam_tests <- function(two_hour_df) {
  gam_df <- two_hour_df %>%
    mutate(roi_label = factor(roi_label, levels = roi_levels)) %>%
    filter(!is.na(mean_temp_c), !is.na(transit_count), !is.na(roi_label))

  if (nrow(gam_df) == 0) {
    return(NULL)
  }

  # NB GAM handles overdispersion and many zero-count 2-hour bins better than Gaussian models.
  m_temp_only <- gam(
    transit_count ~ s(mean_temp_c, k = 6),
    data = gam_df,
    family = nb(link = "log"),
    method = "ML"
  )
  m_temp_by_nest <- gam(
    transit_count ~ roi_label + s(mean_temp_c, k = 6) + s(mean_temp_c, by = roi_label, k = 6),
    data = gam_df,
    family = nb(link = "log"),
    method = "ML"
  )

  bic_tbl <- tibble(
    model = c("gam_temp_only", "gam_temp_by_nest"),
    bic = c(BIC(m_temp_only), BIC(m_temp_by_nest))
  ) %>%
    mutate(delta_bic = bic - min(bic, na.rm = TRUE))

  lrt <- anova(m_temp_only, m_temp_by_nest, test = "Chisq")
  lrt_tbl <- as.data.frame(lrt) %>%
    tibble::rownames_to_column("model") %>%
    as_tibble()

  extract_parametric <- function(mod, model_name) {
    ptab <- summary(mod)$p.table
    tibble(
      model = model_name,
      term = rownames(ptab),
      estimate = ptab[, 1],
      std_error = ptab[, 2],
      statistic = ptab[, 3],
      p_value = ptab[, 4]
    )
  }
  extract_smooth <- function(mod, model_name) {
    stab <- summary(mod)$s.table
    tibble(
      model = model_name,
      term = rownames(stab),
      edf = stab[, "edf"],
      ref_df = stab[, "Ref.df"],
      statistic = stab[, ncol(stab) - 1],
      p_value = stab[, ncol(stab)]
    )
  }

  list(
    bic = bic_tbl,
    lrt = lrt_tbl,
    parametric = bind_rows(
      extract_parametric(m_temp_only, "gam_temp_only"),
      extract_parametric(m_temp_by_nest, "gam_temp_by_nest")
    ),
    smooth = bind_rows(
      extract_smooth(m_temp_only, "gam_temp_only"),
      extract_smooth(m_temp_by_nest, "gam_temp_by_nest")
    )
  )
}

main <- function() {
  cli <- parse_cli_args()
  base_dir <- normalizePath(cli$base_dir, mustWork = TRUE)
  output_dir <- cli$output_dir %||% file.path(base_dir, "batch_runs", "analysis_osmia4_events_weather")
  dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

  weather_dirs_default <- c(
    base_dir,
    dirname(base_dir),
    "temp_data",
    "temp_data/envLogger"
  )
  weather_dirs <- if (is.null(cli$weather_dirs)) weather_dirs_default else cli$weather_dirs

  message("Base dir: ", base_dir)
  message("Run tag: ", cli$run_tag)
  message("Output dir: ", output_dir)
  message("Unit focus: ", cli$unit)

  events_all <- load_all_events(base_dir = base_dir, run_tag = cli$run_tag, tz_name = cli$tz)
  events_io <- events_all %>%
    filter(transit_io %in% c("in", "out"), !is.na(roi_num), !is.na(event_datetime), unit == normalize_unit(cli$unit)) %>%
    mutate(
      roi_label = recode(as.character(roi_num), !!!as.list(roi_letter_map), .default = NA_character_),
      roi_label = factor(roi_label, levels = roi_levels)
    ) %>%
    filter(!is.na(roi_label))

  if (nrow(events_io) == 0) {
    stop("No in/out events found for unit ", cli$unit, " in run_tag ", cli$run_tag)
  }
  message("Filtered to ROI set K-Q (original ROI 2-8); excluded original ROI 1 and ROI 9.")

  write_csv(events_all, file.path(output_dir, "events_all_combined_raw.csv"))
  write_csv(events_io, file.path(output_dir, "events_osmia4_in_out_combined.csv"))

  weather_df <- load_weather_data(weather_dirs = weather_dirs, tz_name = cli$tz, unit_focus = cli$unit)
  if (nrow(weather_df) > 0) {
    write_csv(weather_df, file.path(output_dir, "weather_osmia4_combined.csv"))
  } else {
    message("No matching weather data found; two-hour summary will have NA temperatures.")
  }
  make_event_scatter_plot(events_io, weather_df, output_dir)

  two_hour <- make_two_hour_summary(events_io = events_io, weather_df = weather_df)
  write_csv(two_hour, file.path(output_dir, "osmia4_roi_2h_transits_with_temp.csv"))
  make_weather_plots(two_hour, output_dir, tz_name = cli$tz)

  validation_summary <- make_validation_summary(
    events_all = events_all,
    events_io = events_io,
    two_hour_df = two_hour,
    tz_name = cli$tz
  )
  write_csv(validation_summary, file.path(output_dir, "osmia4_validation_dataset_summary.csv"))
  message("Validation summary: videos tracked = ",
          validation_summary$value[validation_summary$metric == "total_videos_tracked"],
          "; inferred foraging transits = ",
          validation_summary$value[validation_summary$metric == "total_foraging_transits_inferred"])

  kw_out <- run_nest_block_nonparametric_test(two_hour_df = two_hour, tz_name = cli$tz)
  if (!is.null(kw_out)) {
    write_csv(kw_out$kruskal_summary, file.path(output_dir, "osmia4_kruskal_transits_by_nest_2h_daylight.csv"))
    write_csv(kw_out$pairwise_wilcox, file.path(output_dir, "osmia4_pairwise_wilcox_transits_by_nest_2h_daylight.csv"))
    message("Kruskal-Wallis (daylight 2-hour bins) p = ",
            signif(kw_out$kruskal_summary$p_value[[1]], 4))
  }

  gam_out <- run_temperature_gam_tests(two_hour_df = two_hour)
  if (!is.null(gam_out)) {
    write_csv(gam_out$bic, file.path(output_dir, "osmia4_gam_temperature_bic_comparison.csv"))
    write_csv(gam_out$lrt, file.path(output_dir, "osmia4_gam_temperature_model_anova.csv"))
    write_csv(gam_out$parametric, file.path(output_dir, "osmia4_gam_temperature_parametric_terms.csv"))
    write_csv(gam_out$smooth, file.path(output_dir, "osmia4_gam_temperature_smooth_terms.csv"))
    best_model <- gam_out$bic %>% arrange(bic) %>% slice(1)
    message("GAM BIC best model: ", best_model$model[[1]], " (BIC = ", round(best_model$bic[[1]], 2), ")")
  }

  rel_out <- make_foraging_cells_relationship(two_hour, output_dir, tz_name = cli$tz)
  if (!is.null(rel_out)) {
    write_csv(rel_out$summary, file.path(output_dir, "osmia4_nest_foraging_vs_cells_summary.csv"))
    coef_mat <- summary(rel_out$model)$coefficients
    rel_coef <- tibble(
      term = rownames(coef_mat),
      estimate = coef_mat[, "Estimate"],
      std_error = coef_mat[, "Std. Error"],
      statistic = coef_mat[, "t value"],
      p_value = coef_mat[, "Pr(>|t|)"]
    )
    write_csv(rel_coef, file.path(output_dir, "osmia4_nest_foraging_vs_cells_lm_coefficients.csv"))
  }

  message("Done.")
  message("Wrote combined events, summary tables, and plots to: ", output_dir)
}

main()
