import syntropy_sdk
import datetime

def get_configuration(api_key=""):
    config = syntropy_sdk.Configuration()
    config.host = "https://controller-prod-server.syntropystack.com"
    if api_key != "":
        config.api_key["Authorization"] = api_key
    return config


def get_date_after_years(years):
    delta = datetime.timedelta(days=5 * 365)
    return (datetime.datetime.utcnow() + delta).isoformat() + "Z"

class ApiManager:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.auth_api = syntropy_sdk.AuthApi(
            syntropy_sdk.ApiClient(get_configuration())
        )
        self.platform_api = None
        self.login()

    def login(self):
        body = syntropy_sdk.UserLoginObject(self.username, self.password)
        response = self.auth_api.auth_external_login(body)
        config = get_configuration(api_key=response.access_token)
        self.platform_api = syntropy_sdk.PlatformApi(syntropy_sdk.ApiClient(config))

    def get_or_create_api_key(self, name):
        get_api_key_response = self.platform_api.platform_api_key_index(
            filter="api_key_name:{0}".format(name)
        )
        data = get_api_key_response["data"]
        
        if len(data) > 0:
           return -1

        body = {
            "api_key_name": name,
            "api_key_valid_until": get_date_after_years(5),
        }
        create_api_key_response = self.platform_api.platform_api_key_create(body)
        print(create_api_key_response)

        return create_api_key_response["data"]
        
    def get_endpoints(self, name):
        endpoints = self.platform_api.platform_agent_index(filter="name:{0}".format(name))
        return endpoints['data']   

    def recreate_network(self, name):
        networks = self.platform_api.platform_network_index(filter="name:{0}".format(name))['data']
        if len(networks) != 0:
            network_id = networks[0]["network_id"]
            connections = self.platform_api.platform_connection_index(filter="networks[]:{0}".format(network_id))['data']
            for connection in connections:
                self.platform_api.platform_connection_destroy_deprecated(connection["agent_connection_id"])
            self.platform_api.platform_network_destroy(network_id)

        network = self.platform_api.platform_network_create({
            "network_name": name,
            "network_type": syntropy_sdk.MetadataNetworkType.P2P,
            "network_disable_sdn_connections": True,
            "network_metadata": {
                "network_created_by": syntropy_sdk.NetworkGenesisType.SDK,
                "network_type": "P2P"
            }
        })
        return network["data"]
        
    def add_connections(self, network_id, connections):
        print(connections)
        body = {
            "network_id": network_id,
            "network_update_by": syntropy_sdk.NetworkGenesisType.SDK,
            "agent_ids": connections
        }

        self.platform_api.platform_connection_create(body=body)
        connections = self.platform_api.platform_connection_index(filter="networks[]:{0}".format(network_id))['data']
        return connections

    def get_services(self, agent_ids):
        return self.platform_api.platform_agent_service_index(agent_ids)["data"]

    def enable_service(self, connection_id, service_id):
        body = {
            "connectionId": connection_id,
            "changes": [
                {
                    "isEnabled": True,
                    "agentServiceSubnetId": service_id
                } 
            ]
        } 

        self.platform_api.platform_connection_service_update(body)