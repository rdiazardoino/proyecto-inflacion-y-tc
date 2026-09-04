(function() {

    var context = {
        renderTo: undefined,
        senchaApp: undefined,
        senchaRootCnt: undefined,
        spec: undefined,
        jsonData: undefined,
        jolapQuery: undefined,
        errorEnable: false,
        parser: new X2JS({
            'attributePrefix': '@'
        })
    };

    window.addEventListener('resize', function() {
        // se encarga de hacer el actualizar layout de sencha
        // al cambiar tama�o de pantalla

        var me = this;

        if (me.senchaApp != undefined) {
            me.senchaRootCnt.updateLayout({
                isRoot: true
            });
        }

    }.bind(context));

    function receiveSynchronizerEvent(name, data) {
        console.log("O3HTMLCommunicationBus receiveSynchronizerEvent name= " + name);

        adhoc_recieve_event(data);
    }

    function checkSenchaInstance(context) {
        var node = document.getElementById(context.renderTo);

        if (node === null || node.childElementCount == 0 || context.errorEnable) {

            if (context.errorEnable) {
                deleteChildren(node);
            }

            context.senchaRootCnt = Ext.create("Ext.container.Container", {
                renderTo: context.renderTo,
                layout: 'fit',
                border: false,
                width: '100%',
                height: '100%',
                items: context.senchaApp
            });
            context.errorEnable = false;
        } else {

            context.senchaApp.build();
        }
    }

    function showMessage(context) {
        var node = document.getElementById(context.renderTo);

        deleteChildren(node);

        Ext.create("Ext.container.Container", {
            html: context.errorMessage,
            renderTo: context.renderTo,
            width: '100%',
            padding: 5,
            border: false
        });

        viewReady();
    }

    function deleteChildren(node) {
        if (node !== null && node.childElementCount > 0) {
            while (node.firstChild) {
                node.removeChild(node.firstChild);
            }
        }
    }

    function viewReady() {
        adhoc_update_state("view_ready");
    }

    function eventListener(eventName, eventObj) {
        executor(eventObj);
    }

    function executor(eventObj) {

        var me = this,
            i = 0,
            length = eventObj.length,
            node,
            task,
            config,
            data,
            callViewReady = true;

        try {
            for (; i < length; i++) {

                task = eventObj[i];
                data = task.source;

                console.log(task.type);

                switch (task.type) {

                    case "o3::html::task::show-error":

                        context.errorMessage = data;
                        context.errorEnable = true;

                        showMessage(context);

                        break;

                    case "o3::html::task::initialcontext":
                        context.contextPath = data.contextPath;
                        context.renderTo = data.renderTo;
                        context.sessionId = data.sessionId;
                        context.portletId = data.portletId;
                        context.idsLang = data.idsLang;
                        context.user = data.user;
                        if (data.spec) {
                            context.spec = JSON.parse(data.spec);
                        }
                        context.ticket = data.ticket;
                        context.serviceURL_processCommand = data.serviceURL_processCommand;

                        if (context.contextPath != "") {
                            context.contextPath = context.contextPath + "/";
                        }

                        Ext.Loader.setConfig({
                            disableCaching: false,
                            paths: {
                                DashletHTML: context.contextPath + 'DashletHTML/app',
                                GridHTML: context.contextPath + 'GridHTML/app',
                                ChartHTML: context.contextPath + 'ChartHTML/app',
                                ViewDashlet: context.contextPath + 'ViewDashlet/app'
                            }
                        });

                        if (context.spec && context.spec.contextSettings.synchronizationConfig.synchronizerSend) {
                            ClientCommunicationBus.addListener(receiveSynchronizerEvent.bind(me), context.spec.contextSettings.synchronizationConfig.synchronizerSend);
                        }

                        break;
                    case "o3::html::task::new-data":

                        context.jsonData = data;

                        break;
                    case "o3::html::task::put-loading":

                        node = document.getElementById(context.renderTo);

                        if (node)
                            node.className += " Loader";

                        break;
                    case "o3::html::task::remove-loading":

                        node = document.getElementById(context.renderTo);

                        if (node)
                            node.className = node.className.replace(/Loader/g, '');

                        break;
                    case "o3::html::task::new-spec":
                        context.spec = context.parser.xml_str2json(data).view;
                        break;
                    case "o3::html::task::refresh":

                        context.spec.laf.viewSpec.type = data;

                        context.senchaApp.setSpec(context.spec, {
                            update: true
                        });
                        context.senchaApp.RestServices.setData(context.jsonData);

                        context.senchaApp.build();

                        node = document.getElementById(context.renderTo);
                        node.className = node.className.replace(/Loader/g, '');

                        break;

                    case "o3::html::task::render":

                        node = document.getElementById(context.renderTo);

                        while (node.firstChild) {
                            node.removeChild(node.firstChild);
                        }

                        context.spec.laf.viewSpec.type = data;
                        context.senchaApp = Ext.create("ViewDashlet.view.ViewDashlet");

                        context.senchaApp.initDummyMode({
                            sessionId: context.sessionId,
                            idsLang: context.idsLang
                        }, undefined, {
                            viewMode: 'EDIT'
                        });

                        context.senchaApp.RestServices.setData(context.jsonData);

                        context.senchaApp.setSpec(context.spec, {
                            update: true
                        });

                        checkSenchaInstance(context);
                        node.className = node.className.replace(/Loader/g, '');

                        break;
                    case "o3::html::task::new-jolap-query":

                        context.jolapQuery = data;

                        break;
                    case "o3::html::task::refresh-adhoc-mode":

                        context.senchaApp.RestServices.setJOlapQuery(context.jolapQuery);
                        context.senchaApp.RestServices.buildRequest();

                        checkSenchaInstance(context);

                        node = document.getElementById(context.renderTo);
                        node.className = node.className.replace(/Loader/g, '');

                        break;

                    case "o3::html::task::render-adhoc-mode":

                        context.busy = true;

                        node = document.getElementById(context.renderTo);

                        while (node.firstChild) {
                            node.removeChild(node.firstChild);
                        }

                        context.senchaApp = Ext.create("ViewDashlet.view.ViewDashlet", {
                            detachOnRemove: false
                        });

                        context.senchaApp.setRenderListener(viewReady);

                        config = {
                            Ticket: context.ticket,
                            User: context.user,
                            sessionId: context.sessionId,
                            idO3ClientSSO: "<%= idO3ClientSSO %>",
                            idsLang: context.idsLang,
                            url: context.serviceURL_processCommand,
                            exportURL: "<%= serviceURL_export %>",
                            withCredentials: true,
                            directCall: true,
                            portletID: context.portletId,
                            Accept: "application/is-grid+json",
                            urlPrefixPortal: '<%= urlPrefixPortal %>/O3DashletNavigatorServlet',
                            namespace: "${namespace}",
                            viewDashlet_timeout: dashletConfig.viewDashlet_timeout
                        };

                        context.senchaApp.initDashlet(config,
                            context.spec, {
                                defaultChartColors: dashletConfig.defaultChartColors,
                                heightNull: "500px",
                                viewMode: 'VIEW',
                                prefixUrl: "/ViewDashlet/"
                            });

                        context.senchaApp.RestServices.setJOlapQuery(context.jolapQuery);

                        context.senchaApp.setSpec(context.spec, {
                            update: true
                        });

                        checkSenchaInstance(context);

                    case "o3::html::task::refresh-layout":
                        if (context.senchaRootCnt) {
                            context.senchaRootCnt.updateLayout({ isRoot: true });
                        }
                        break;

                }
            }
        } catch (e) {
            console.log(e);
        }

    }

    ClientCommunicationBus.addListener(eventListener, "o3::html::event::bus");

})();