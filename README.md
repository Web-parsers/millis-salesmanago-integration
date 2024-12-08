# Millis with SalesManago integration

This FastAPI is an adapter between SalesManago and Millis.

## Flow

There is a workflow in SalesManago that should do phone calling and based on outcomes reassign tags, update info, move people to another stages.
For the integration we should trigger Millis to call a person (in reality a bunch of persons within their availability timezones) and receive a response. Based  on this respond we should automatically decide whether it's a client or we should recall, don't call them anymore, there are issues and we should contact manually etc.

