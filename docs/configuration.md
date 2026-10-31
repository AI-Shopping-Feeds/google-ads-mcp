# Advanced configuration

## Configuring and Namespacing Tools

The Google Ads MCP server uses the `tools_config.yaml` to let you selectively enable or disable individual tools or tool categories (namespaces) and customize their namespace prefixes.

A default `tools_config.yaml` with all tools enabled is bundled with the package, so the server works out of the box with no extra setup. To customize your installation, the server resolves the configuration in the following order:

1. An explicit path set via the `GOOGLE_ADS_MCP_TOOLS_CONFIG` environment variable.
2. A `tools_config.yaml` file in the current working directory.
3. The default `tools_config.yaml` bundled with the package.

If an explicitly requested configuration file (via the environment variable) is missing, or any resolved file is invalid, the server raises an error and fails to start.

### Configuration Example:
```yaml
namespaces:
  # Option 1: Enable category 'customers' with default prefix -> "customers_list_accessible_customers"
  customers: true

  # Option 2: Enable category 'search' with a custom prefix -> "query_search"
  search: "query"

  # Option 3: Fine-grained control over tools in a category
  metadata:
    enabled: true
    prefix: "metadata"
    enabled_tools:
      - get_resource_metadata: true
```


## Resources available

- `discovery-document`: Retrieve the Google Ads API discovery document. Provides the discovery document for the latest version of the Google Ads API, which describes the API surface, including resources, methods, and schemas. Host LLMs should access this resource to understand the structure of the Google Ads API and discover available features.
- `metrics`: Retrieve information about the metrics available for reporting in the Google Ads API.
- `segments`: Retrieve information about the segments available for reporting in the Google Ads API.
- `release-notes`: Retrieve the release notes for the latest version of the Google Ads API.


## Using an existing `google-ads.yaml`


[Follow the instructions](https://developers.google.com/google-ads/api/docs/client-libs/python/)
to setup and configure the Google Ads API Python client library

If you have already done this and have a working `google-ads.yaml` , you can reuse this file!

In the utils.py file, change get_googleads_client() to use the load_from_storage() method.

