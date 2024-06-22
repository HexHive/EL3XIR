import os
import sys

import click

from secmonRehosting import install_logging
from secmonRehosting.rehostingEnvironments.samsungS6.factories import SecMonS6AvatarFactory


@click.command()
@click.argument("sboot_s6_path")
@click.option("--avatar-output-dir", type=click.Path(exists=False))
def main(sboot_s6_path, avatar_output_dir):

    install_logging()

    if avatar_output_dir:
        print("Using output dir {} with avatar2".format(avatar_output_dir), file=sys.stderr)

        # create directory if it doesn't exist
        # that saves the user from creating it beforehand
        os.makedirs(avatar_output_dir, exist_ok=True)

        factory = SecMonS6AvatarFactory()

        context = factory.get_rehosting_context(sboot_s6_path, avatar_output_dir)

        runner = factory.get_runner(context)

        runner.cont()
        print("S6 SecMonitor booted!")


if __name__ == "__main__":
    main()