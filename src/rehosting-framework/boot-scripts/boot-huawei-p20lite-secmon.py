import os
import sys

import click

from secmonRehosting import install_logging
from secmonRehosting.rehostingEnvironments.huaweiP20.factories import SecMonP20AvatarFactory

@click.command()
@click.argument("secmon_binary_path")
@click.option("--avatar-output-dir", type=click.Path(exists=False))
def main(secmon_binary_path, avatar_output_dir):

    install_logging()

    if avatar_output_dir:
        print("Using output dir {} with avatar2".format(avatar_output_dir), file=sys.stderr)

        # create directory if it doesn't exist
        # that saves the user from creating it beforehand
        os.makedirs(avatar_output_dir, exist_ok=True)

        factory = SecMonP20AvatarFactory()

        context = factory.get_rehosting_context(secmon_binary_path, avatar_output_dir)

        runner = factory.get_runner(context)

        runner.cont()
        print("P20 SecMonitor booted!")


if __name__ == "__main__":
    main()