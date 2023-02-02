import contextlib
import logging
import os.path

import requests
import uvicorn

from jarvis.executors.port_handler import is_port_in_use, kill_port_pid
from jarvis.modules.exceptions import EgressErrors
from jarvis.modules.logger import config
from jarvis.modules.logger.custom_logger import logger
from jarvis.modules.models import models


class APIServer(uvicorn.Server):
    """Shared servers state that is available between all protocol instances.

    >>> APIServer

    See Also:
        Overrides `uvicorn.server.Server <https://github.com/encode/uvicorn/blob/master/uvicorn/server.py#L48>`__

    References:
        https://github.com/encode/uvicorn/issues/742#issuecomment-674411676
    """

    def install_signal_handlers(self) -> None:
        """Overrides ``install_signal_handlers`` in ``uvicorn.Server`` module."""
        pass

    @contextlib.contextmanager
    def run_in_parallel(self) -> None:
        """Initiates ``Server.run`` in a dedicated process."""
        self.run()


def fast_api() -> None:
    """Initiates the fast API in a dedicated process using uvicorn server.

    See Also:
        - Checks if the port is being used. If so, makes a ``GET`` request to the endpoint.
        - Attempts to kill the process listening to the port, if the endpoint doesn't respond.
    """
    api_config = config.APIConfig()
    config.multiprocessing_logger(filename=api_config.DEFAULT_LOG_FILENAME,
                                  log_format=logging.Formatter(api_config.DEFAULT_LOG_FORMAT))
    url = f'http://{models.env.offline_host}:{models.env.offline_port}'

    if is_port_in_use(port=models.env.offline_port):
        logger.info(f'{models.env.offline_port} is currently in use.')

        try:
            res = requests.get(url=url, timeout=1)
            if res.ok:
                logger.info(f'{url!r} is accessible.')
                return
            raise requests.ConnectionError
        except EgressErrors:
            logger.error('Unable to connect to existing uvicorn server.')

        if not kill_port_pid(port=models.env.offline_port):  # This might terminate Jarvis
            logger.critical('ATTENTION::Failed to kill existing PID. Attempting to re-create session.')

    # Uvicorn config supports the module as a value for the arg 'app' which can be from relative imports
    # However, in this case, using relative imports will mess up the logger since the variable is being reused widely
    assert os.path.exists(os.path.join(os.path.dirname(__file__), "fast.py")), \
        "API path has either been modified or unreachable."
    argument_dict = {
        "app": "jarvis.api.fast:app",
        "host": models.env.offline_host,
        "port": models.env.offline_port,
        "ws_ping_interval": 20.0,
        "ws_ping_timeout": 20.0,
        "workers": models.env.workers
    }

    logger.debug(argument_dict)
    logger.info(f"Starting FastAPI on Uvicorn server with {models.env.workers} workers.")

    server_conf = uvicorn.Config(**argument_dict)
    APIServer(config=server_conf).run_in_parallel()
