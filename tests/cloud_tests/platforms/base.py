# This file is part of cloud-init. See LICENSE file for license information.


class Platform(object):
    """
    Base class for platforms
    """
    platform_name = None

    def __init__(self, config):
        """
        Set up platform
        """
        self.config = config

    def get_image(self, img_conf):
        """
        Get image using 'img_conf', where img_conf is a dict containing all
        image configuration parameters

        in this dict there must be a 'platform_ident' key containing
        configuration for identifying each image on a per platform basis

        see implementations for get_image() for details about the contents
        of the platform's config entry

        note: see 'releases' main_config.yaml for example entries

        img_conf: configuration for image
        return_value: cloud_tests.images instance
        """
        raise NotImplementedError

    def destroy(self):
        """
        Clean up platform data
        """
        pass

    def _extract_img_platform_config(self, img_conf):
        """
        extract platform configuration for current platform from img_conf
        """
        platform_ident = img_conf.get('platform_ident')
        if not platform_ident:
            raise ValueError('invalid img_conf, missing \'platform_ident\'')
        ident = platform_ident.get(self.platform_name)
        if not ident:
            raise ValueError('img_conf: {} missing config for platform {}'
                             .format(img_conf, self.platform_name))
        return ident

# vi: ts=4 expandtab
