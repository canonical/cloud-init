.. _cce-chef:

Install and run Chef recipes
****************************

This example file automatically installs the Chef client and runs a list of
recipes when the instance boots for the first time. It should be passed as user
data when starting the instance.

The default is to install from packages.

The key used in this example is from https://packages.chef.io/chef.asc.

For a full list of accepted keys, refer to the :ref:`Chef module <mod_cc_chef>`
schema.

Example 1
=========

.. literalinclude:: ../../../module-docs/cc_chef/example1.yaml
   :language: yaml
   :linenos:

Example 2
=========

.. code-block:: yaml

    #cloud-config
    apt:
      sources:
        source1:
          source: "deb http://packages.chef.io/repos/apt/stable $RELEASE main"
          key: |
            -----BEGIN PGP PUBLIC KEY BLOCK-----
            Version: GnuPG v1.4.12 (Darwin)
            Comment: GPGTools - http://gpgtools.org
            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
            zA==
            =IxPr
            -----END PGP PUBLIC KEY BLOCK-----
    chef:
      chef_license: accept
      encrypted_data_bag_secret: /etc/chef/encrypted_data_bag_secret
      environment: production
      force_install: false
      initial_attributes:
        apache:
          prefork: {maxclients: 100}
          keepalive: false
      install_type: packages
      node_name: your-node-name
      omnibus_url: https://www.chef.io/chef/install.sh
      omnibus_version: 12.3.0
      run_list: ['recipe[apache2]', 'role[db]']
      server_url: https://chef.yourorg.com
      validation_name: yourorg-validator
      validation_cert: |
        -----BEGIN RSA PRIVATE KEY-----
        YOUR-ORGS-VALIDATION-KEY-HERE
        -----END RSA PRIVATE KEY-----

.. note::
   - ``chef_license``: Valid values are 'accept' and 'accept-no-persist'.
   - ``install_type``: Valid values are 'gems', 'packages' and 'omnibus'. If
     ``install_type`` is 'omnibus', pass pinned version string to the install
     script via ``omnibus_version``, and change the url to download via
     ``omnibus_url``.
   - ``force_install``: (boolean) run ``install_type`` code even if
     ``chef-client`` appears to be already installed.
   - If ``validation_cert``'s value is "system" then it is expected that the
     file already exists on the system.
   - If encrypted data bags are used, the client needs to have a secrets file
     configured to decrypt them


Chef oneiric
============

This example file, as in the example above, automatically installs the Chef
client and runs a list of recipes when the instance boots for the first time.

However, in this case, the example uses the instance 11.10 (oneiric). The file
should be passed as user-data when starting the instance.

The default is to install from packages.

The key used in this example is from
https://packages.chef.io/chef.asc

.. code-block:: yaml

    #cloud-config
    apt:
      sources:
         source1:
            source: "deb http://apt.opscode.com/ $RELEASE-0.10 main"
            key: |
             -----BEGIN PGP PUBLIC KEY BLOCK-----
             Version: GnuPG v1.4.9 (GNU/Linux)
             mQGiBEppC7QRBADfsOkZU6KZK+YmKw4wev5mjKJEkVGlus+NxW8wItX5sGa6kdUu
             twAyj7Yr92rF+ICFEP3gGU6+lGo0Nve7KxkN/1W7/m3G4zuk+ccIKmjp8KS3qn99
             dxy64vcji9jIllVa+XXOGIp0G8GEaj7mbkixL/bMeGfdMlv8Gf2XPpp9vwCgn/GC
             JKacfnw7MpLKUHOYSlb//JsEAJqao3ViNfav83jJKEkD8cf59Y8xKia5OpZqTK5W
             ShVnNWS3U5IVQk10ZDH97Qn/YrK387H4CyhLE9mxPXs/ul18ioiaars/q2MEKU2I
             XKfV21eMLO9LYd6Ny/Kqj8o5WQK2J6+NAhSwvthZcIEphcFignIuobP+B5wNFQpe
             DbKfA/0WvN2OwFeWRcmmd3Hz7nHTpcnSF+4QX6yHRF/5BgxkG6IqBIACQbzPn6Hm
             sMtm/SVf11izmDqSsQptCrOZILfLX/mE+YOl+CwWSHhl+YsFts1WOuh1EhQD26aO
             Z84HuHV5HFRWjDLw9LriltBVQcXbpfSrRP5bdr7Wh8vhqJTPjrQnT3BzY29kZSBQ
             YWNrYWdlcyA8cGFja2FnZXNAb3BzY29kZS5jb20+iGAEExECACAFAkppC7QCGwMG
             CwkIBwMCBBUCCAMEFgIDAQIeAQIXgAAKCRApQKupg++Caj8sAKCOXmdG36gWji/K
             +o+XtBfvdMnFYQCfTCEWxRy2BnzLoBBFCjDSK6sJqCu5Ag0ESmkLtBAIAIO2SwlR
             lU5i6gTOp42RHWW7/pmW78CwUqJnYqnXROrt3h9F9xrsGkH0Fh1FRtsnncgzIhvh
             DLQnRHnkXm0ws0jV0PF74ttoUT6BLAUsFi2SPP1zYNJ9H9fhhK/pjijtAcQwdgxu
             wwNJ5xCEscBZCjhSRXm0d30bK1o49Cow8ZIbHtnXVP41c9QWOzX/LaGZsKQZnaMx
             EzDk8dyyctR2f03vRSVyTFGgdpUcpbr9eTFVgikCa6ODEBv+0BnCH6yGTXwBid9g
             w0o1e/2DviKUWCC+AlAUOubLmOIGFBuI4UR+rux9affbHcLIOTiKQXv79lW3P7W8
             AAfniSQKfPWXrrcAAwUH/2XBqD4Uxhbs25HDUUiM/m6Gnlj6EsStg8n0nMggLhuN
             QmPfoNByMPUqvA7sULyfr6xCYzbzRNxABHSpf85FzGQ29RF4xsA4vOOU8RDIYQ9X
             Q8NqqR6pydprRFqWe47hsAN7BoYuhWqTtOLSBmnAnzTR5pURoqcquWYiiEavZixJ
             3ZRAq/HMGioJEtMFrvsZjGXuzef7f0ytfR1zYeLVWnL9Bd32CueBlI7dhYwkFe+V
             Ep5jWOCj02C1wHcwt+uIRDJV6TdtbIiBYAdOMPk15+VBdweBXwMuYXr76+A7VeDL
             zIhi7tKFo6WiwjKZq0dzctsJJjtIfr4K4vbiD9Ojg1iISQQYEQIACQUCSmkLtAIb
             DAAKCRApQKupg++CauISAJ9CxYPOKhOxalBnVTLeNUkAHGg2gACeIsbobtaD4ZHG
             0GLl8EkfA8uhluM=
             =zKAm
             -----END PGP PUBLIC KEY BLOCK-----
    chef:
      environment: "production"
      initial_attributes:
        apache:
          keepalive: false
          prefork: {maxclients: 100}
      install_type: packages
      node_name: your-node-name
      run_list: ['recipe[apache2]', 'role[db]']
      server_url: https://chef.yourorg.com:4000
      validation_cert: unused
      validation_name: yourorg-validator
      validation_key: |
        -----BEGIN RSA PRIVATE KEY-----
        YOUR-ORGS-VALIDATION-KEY-HERE
        -----END RSA PRIVATE KEY-----

.. note::
   11.10 will fail if ``install_type`` is "gems" (LP: #960576).

   The value of ``validation_cert`` is not used if ``validation_key`` is
   defined, but the variable needs to be defined (LP: #960547).

.. LINKS
.. _chef: http://www.chef.io/chef/

