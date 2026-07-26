package com.ingomob.dq;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/**
 * Dependency-free data-quality gate for the Ingolstadt open-data feeds.
 *
 * <p>Validates the raw CSV/GTFS sources against schema and business rules
 * (non-negative counts, referential uniqueness, geographic bounding box,
 * valid date formats) and emits a machine-readable JSON report. Exits non-zero
 * when any rule fails, so it can act as a CI gate before the Python pipeline
 * ingests the data.
 */
public class DataQualityValidator {

    static final double MIN_LAT = 48.71, MAX_LAT = 48.82, MIN_LON = 11.35, MAX_LON = 11.50;

    static class Check {
        final String name;
        final String table;
        int passed = 0;
        int failed = 0;
        final List<String> samples = new ArrayList<>();

        Check(String name, String table) {
            this.name = name;
            this.table = table;
        }

        void record(boolean ok, String issue) {
            if (ok) {
                passed++;
            } else {
                failed++;
                if (samples.size() < 5) {
                    samples.add(issue);
                }
            }
        }
    }

    static List<String[]> readCsv(Path p) throws IOException {
        List<String[]> rows = new ArrayList<>();
        for (String line : Files.readAllLines(p)) {
            rows.add(line.split(",", -1));
        }
        return rows;
    }

    static Map<String, Integer> header(String[] h) {
        Map<String, Integer> m = new HashMap<>();
        for (int i = 0; i < h.length; i++) {
            m.put(h[i].trim(), i);
        }
        return m;
    }

    public static void main(String[] args) throws IOException {
        Path raw = Paths.get(args.length > 0 ? args[0] : "data/raw");
        Path out = Paths.get(args.length > 1 ? args[1] : "data/processed/data_quality_report.json");
        List<Check> checks = new ArrayList<>();
        long total = 0;

        Path traffic = raw.resolve("traffic_counts.csv");
        Check tNeg = new Check("vehicle_count_non_negative", "traffic_counts");
        Check tDup = new Check("no_duplicate_detector_hour", "traffic_counts");
        Check tDate = new Check("valid_date_format", "traffic_counts");
        Check tHour = new Check("hour_in_range", "traffic_counts");
        if (Files.exists(traffic)) {
            List<String[]> rows = readCsv(traffic);
            Map<String, Integer> h = header(rows.get(0));
            Set<String> seen = new HashSet<>();
            for (int i = 1; i < rows.size(); i++) {
                String[] r = rows.get(i);
                total++;
                String det = r[h.get("detector_id")];
                String date = r[h.get("date")];
                String hour = r[h.get("hour")];
                int vc = pi(r[h.get("vehicle_count")]);
                tNeg.record(vc >= 0, "row " + i + " detector " + det + " count " + r[h.get("vehicle_count")]);
                tDate.record(date.matches("\\d{4}-\\d{2}-\\d{2}"), "row " + i + " date " + date);
                tDup.record(seen.add(det + "|" + date + "|" + hour), "dup " + det + "|" + date + "|" + hour);
                int hv = pi(hour);
                tHour.record(hv >= 0 && hv <= 23, "row " + i + " hour " + hour);
            }
        }
        checks.add(tNeg);
        checks.add(tDup);
        checks.add(tDate);
        checks.add(tHour);

        Path charging = raw.resolve("charging_stations.csv");
        Check cPow = new Check("power_kw_positive", "charging_stations");
        Check cGeo = new Check("coords_within_bbox", "charging_stations");
        Check cPts = new Check("num_points_ge_1", "charging_stations");
        if (Files.exists(charging)) {
            List<String[]> rows = readCsv(charging);
            Map<String, Integer> h = header(rows.get(0));
            for (int i = 1; i < rows.size(); i++) {
                String[] r = rows.get(i);
                total++;
                cPow.record(pi(r[h.get("power_kw")]) > 0, "row " + i);
                cGeo.record(inBox(pd(r[h.get("lat")]), pd(r[h.get("lon")])), "row " + i);
                cPts.record(pi(r[h.get("num_points")]) >= 1, "row " + i);
            }
        }
        checks.add(cPow);
        checks.add(cGeo);
        checks.add(cPts);

        Path stops = raw.resolve("gtfs/stops.txt");
        Check sGeo = new Check("stop_coords_within_bbox", "gtfs_stops");
        Check sUniq = new Check("stop_id_unique", "gtfs_stops");
        if (Files.exists(stops)) {
            List<String[]> rows = readCsv(stops);
            Map<String, Integer> h = header(rows.get(0));
            Set<String> ids = new HashSet<>();
            for (int i = 1; i < rows.size(); i++) {
                String[] r = rows.get(i);
                total++;
                sGeo.record(inBox(pd(r[h.get("stop_lat")]), pd(r[h.get("stop_lon")])), "row " + i);
                sUniq.record(ids.add(r[h.get("stop_id")]), "dup " + r[h.get("stop_id")]);
            }
        }
        checks.add(sGeo);
        checks.add(sUniq);

        boolean allPassed = true;
        for (Check c : checks) {
            if (c.failed > 0) {
                allPassed = false;
            }
        }
        Files.createDirectories(out.getParent());
        Files.write(out, toJson(checks, total, allPassed).getBytes("UTF-8"));
        System.out.println("[DQ] rows checked=" + total + " checks=" + checks.size() + " all_passed=" + allPassed);
        for (Check c : checks) {
            System.out.println(String.format("  - %-28s %-18s pass=%d fail=%d", c.name, c.table, c.passed, c.failed));
        }
        if (!allPassed) {
            System.err.println("[DQ] data-quality FAILED");
            System.exit(2);
        }
    }

    static double pd(String s) {
        try {
            return Double.parseDouble(s.trim());
        } catch (Exception e) {
            return Double.NaN;
        }
    }

    static int pi(String s) {
        try {
            return Integer.parseInt(s.trim());
        } catch (Exception e) {
            return -1;
        }
    }

    static boolean inBox(double lat, double lon) {
        return lat >= MIN_LAT && lat <= MAX_LAT && lon >= MIN_LON && lon <= MAX_LON;
    }

    static String esc(String s) {
        return s.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    static String toJson(List<Check> checks, long total, boolean all) {
        StringBuilder b = new StringBuilder();
        b.append("{\n  \"generated_at\": \"").append(java.time.OffsetDateTime.now()).append("\",\n");
        b.append("  \"total_rows_checked\": ").append(total).append(",\n");
        b.append("  \"all_passed\": ").append(all).append(",\n  \"checks\": [\n");
        for (int i = 0; i < checks.size(); i++) {
            Check c = checks.get(i);
            b.append("    {\"name\": \"").append(c.name).append("\", \"table\": \"").append(c.table)
             .append("\", \"passed\": ").append(c.passed).append(", \"failed\": ").append(c.failed)
             .append(", \"sample_issues\": [");
            for (int j = 0; j < c.samples.size(); j++) {
                if (j > 0) {
                    b.append(", ");
                }
                b.append("\"").append(esc(c.samples.get(j))).append("\"");
            }
            b.append("]}").append(i < checks.size() - 1 ? "," : "").append("\n");
        }
        b.append("  ]\n}\n");
        return b.toString();
    }
}
