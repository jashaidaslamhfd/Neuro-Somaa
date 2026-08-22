# YouTube Shorts metric research notes

## Official sources

1. YouTube Analytics API metrics: https://developers.google.com/youtube/analytics/metrics
2. YouTube Analytics API available reports: https://developers.google.com/youtube/analytics/v2/available_reports
3. YouTube Help — Understand your YouTube video reach: https://support.google.com/youtube/answer/9314355?hl=en

## Key findings

The official Analytics API metrics page defines `engagedViews` as the number of times a channel video was viewed past the initial seconds. It defines `averageViewDuration` as the average length of video playbacks and `averageViewPercentage` as the average percentage of a video watched during a playback.

The official YouTube Help Reach page exposes Shorts-related Reach terminology including `Stayed to watch`, defined as the percentage of times viewers stayed to watch past the initial seconds of a Short. The page also describes views, average view duration, thumbnail impressions, and traffic sources. It notes that some reports may not be available on mobile devices.

The official available-reports documentation distinguishes targeted YouTube Analytics API queries from bulk Reporting API reports. It states that Reach reports are supported for channels through bulk reports, while the Analytics API supports targeted video/activity queries. Therefore, the integration should probe supported Analytics metrics and preserve `unavailable` status rather than inventing values when a Studio Reach metric is not exposed by the targeted endpoint.

## Implementation implication

The repository should request supported activity metrics such as `views`, `engagedViews`, `averageViewDuration`, `averageViewPercentage`, `likes`, `comments`, `shares`, and `subscribersGained` where compatible. It should separately probe candidate Shorts/feed fields such as `shortsFeedShown`, `stayedToWatch`, `viewedVsSwipedAway`, or equivalent only if the endpoint accepts them. Unsupported identifiers must be dropped per query and persisted as unavailable. `impressions` and CTR should not be assumed to represent Shorts-feed exposure when the API does not return them for the channel/query combination.
