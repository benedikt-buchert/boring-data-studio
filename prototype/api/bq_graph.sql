-- Wayfinder #21, U-30..U-32: native baseline with BigQuery graph measures (GA 2026-11-11).
-- The flights model of flights.yml as a property graph, for the native Data Studio BigQuery connector.
-- NOT RUN YET: written without BigQuery access. Check the syntax against
-- https://docs.cloud.google.com/bigquery/docs/graph-measures before the live run.
-- Replace my-project.bsl_spike with the dataset of runbook step 1.
--
-- Not in the graph:
--   median_delay   graph measures support SUM, AVG, COUNT, MIN, MAX only (and AGG).
--   pct_of_total   needs .all() (a total over all groups). No measure form exists.
--   COUNT(*)       not permitted in a measure. flight_count counts the key instead.

-- flights has no key column. A graph node table needs a KEY.
CREATE OR REPLACE TABLE `my-project.bsl_spike.flights_keyed` AS
SELECT GENERATE_UUID() AS flight_id, * FROM `my-project.bsl_spike.flights`;

CREATE OR REPLACE PROPERTY GRAPH `my-project.bsl_spike.FlightsGraph`
NODE TABLES (
  `my-project.bsl_spike.flights_keyed` AS Flight KEY (flight_id)
    PROPERTIES (
      flight_id, origin, carrier, dep_date, distance, delay,
      MEASURE(COUNT(flight_id)) AS flight_count
        OPTIONS (description = 'Number of flights'),
      MEASURE(SUM(distance)) AS total_distance
        OPTIONS (description = 'Total distance flown'),
      MEASURE(AVG(distance)) AS avg_distance,
      MEASURE(AVG(delay)) AS avg_delay,
      MEASURE(SUM(delay)) AS total_delay,
      MEASURE(MAX(delay)) AS max_delay,
      MEASURE(MIN(delay)) AS min_delay,
      MEASURE(MAX(distance)) AS max_distance,
      MEASURE(MIN(distance)) AS min_distance,
      MEASURE(SUM(CASE WHEN distance > 2000 THEN 1 ELSE 0 END)) AS long_haul_flights
        OPTIONS (description = 'Flights longer than 2000 miles'),
      MEASURE(SUM(CASE WHEN distance < 500 THEN 1 ELSE 0 END)) AS short_haul_flights
        OPTIONS (description = 'Flights shorter than 500 miles'),
      MEASURE(SUM(CASE WHEN delay < 5 THEN 1 ELSE 0 END)) AS early_flights
        OPTIONS (description = 'Flights delayed less than 5 minutes'),
      MEASURE(SUM(CASE WHEN delay > 30 THEN 1 ELSE 0 END)) AS delayed_flights
        OPTIONS (description = 'Flights delayed more than 30 minutes (conditional measure)'),
      -- E-10: BSL nunique does not count NULL. COUNT(DISTINCT) does not count NULL either.
      MEASURE(COUNT(DISTINCT carrier)) AS unique_carriers
        OPTIONS (description = 'Distinct carriers'),
      MEASURE(SAFE_DIVIDE(AGG(total_distance), NULLIF(AGG(flight_count), 0))) AS distance_per_flight
        OPTIONS (description = 'Average distance per flight'),
      MEASURE(1 - SAFE_DIVIDE(AGG(delayed_flights), NULLIF(AGG(flight_count), 0))) AS on_time_rate
        OPTIONS (description = 'Share of flights delayed 30 min or less')
    ),
  `my-project.bsl_spike.airports` AS Airport KEY (code)
    PROPERTIES (
      code, city, country,
      MEASURE(COUNT(code)) AS airport_count
    )
)
EDGE TABLES (
  `my-project.bsl_spike.flights_keyed` AS DEPARTS_FROM KEY (flight_id)
    SOURCE KEY (flight_id) REFERENCES Flight (flight_id)
    DESTINATION KEY (origin) REFERENCES Airport (code)
    NO PROPERTIES
);

-- Self-check before Data Studio: must equal prototype/truth.py at the origin grain.
-- SELECT Flight_origin, AGG(Flight_flight_count), AGG(Flight_avg_distance),
--        AGG(Flight_unique_carriers), AGG(Flight_on_time_rate)
-- FROM GRAPH_EXPAND("my-project.bsl_spike.FlightsGraph")
-- GROUP BY Flight_origin;
-- Run it with bq query --nouse_cache: a graph change does not invalidate cached GRAPH_EXPAND results.
