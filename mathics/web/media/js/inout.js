function showCreate() {
	requireLogin("You must login to save worksheets online.", function() {
		showPopup($('save'));
	});
}

function showSaveNew() {
	requireLogin("You must login to save worksheets online.", function() {
		showPopup($('saveNew'));
	});
}

function showDelete(name) {
	requireLogin("You must login to delete the worksheet.", function() {
		$('deleteSheetName').setText(name);
		showPopup($('delete'));
	});
}

function openWorksheet(name) {
	hidePopup();
	new Ajax.Request('/ajax/open/', {
		method: 'post',
		parameters: {
			'name': name
		},
		onSuccess: function(transport) {
			var response = transport.responseText.evalJSON();
			if ($('document').visible())
				setContent(response.content);
			else
				$('codetext').value = response.content;
		}
	})
}

function showOpen() {
	requireLogin("You must login to open online worksheets.", function() {
		new Ajax.Request('/ajax/getworksheets/', {
			method: 'get',
			onSuccess: function(transport) {
				var response = transport.responseText.evalJSON();
				var tbody = $('openFilelist'); 
				tbody.deleteChildNodes();
				response.worksheets.each(function(worksheet) {
					tbody.appendChild($E('tr', $E('td',
						$E('a', {'href': 'javascript:openWorksheet("' + worksheet.name + '")'},
							$T(worksheet.name)
						)
					)));
				});
				showPopup($('open'));
			}
		});
	});
}

function cancelCreate() {
	hidePopup();
}

function cancelOpen() {
	hidePopup();
}

function cancelDelete() {
	hidePopup();
}

function cancelSaveNew() {
	hidePopup();
}

function createSheet() {
	submitForm('saveForm', '/ajax/save/', function(response) {
		if (!checkLogin(response))
			return;
		if (response.result == 'overwrite') {
			alert('exists');
		} else {
			hidePopup();
			location.href = '/worksheet/' + response.form.values.name;
		}
	}, {
		'content': [{request: '', results: ''}],
		'overwrite': ''
	});
}

function saveSheet() {
	if (window.saving)
		return;

	if ( window.sheetName == '')
		return showSaveNew();

	window.saving = true;
	clearTimeout(window.saveStatusTimeoutHandler);

	$$('.saveStatus').invoke('hide');
	$('sheetSaving').show();

	var content;
	if ($('document').visible())
		content = getContent();
	else
		content = $('codetext').value;

	new Ajax.Request('/ajax/save/', {
		method: 'post',
		parameters: {
			'name': window.sheetName,
			'content': content,
			'overwrite': true
		},
		onSuccess: function(response) {
			$$('.saveStatus').invoke('hide');
			$('sheetSaved').show();
		},
		onFailure: function(response) {
			$$('.saveStatus').invoke('hide');
			$('sheetUnsaved').show();
		},
		onComplete: function () {
			window.saving = false;
			window.saveStatusTimeoutHandler = setTimeout(function () {
				$$('.saveStatus').invoke('hide');
			}, 1000);
		}
	});
}

function saveNewSheet(name, overwrite) {
	name = (name || $('id_newName').value).trim();

	var content;
	if ($('document').visible())
		content = getContent();
	else
		content = $('codetext').value;

	submitForm('saveNewForm', '/ajax/save/', function(response) {
		console.log(response);
		if (response.result == 'overwrite') {
			var yes = confirm('Worksheet named ' + name + ' exists. Do you want to overwrite it?');
			if (yes) saveSheet(name, overwrite);
			return;
		}

		$$('.saveStatus').invoke('hide');
		$('sheetSaved').show();
		window.saveStatusTimeoutHandler = setTimeout(function () {
			$$('.saveStatus').invoke('hide');
		}, 1000);

		$('id_newName').value = '';
		hidePopup();

		window.sheetName = name;
		history.replaceState({}, 'Mathics', '/worksheet/' + name + '/' + location.hash)
	}, {
		'name': name,
		'content': content,
		'overwrite': overwrite || ''
	});
}

function deleteSheet(name) {
	submitForm('deleteForm', '/ajax/delete/', function(response) {
		if (!checkLogin(response))
			return;
		if (response.result == 'confirm') {
			alert('Enter correct worksheet name to confirm.');
		} else {
			location.reload();
		}
	}, {
		name: $('deleteSheetName').getText(name)
	});
}

function switchCode() {
	if ($('document').visible()) {
		$('document').hide();
		var content = getContent();
		$('codetext').value = content;
		$('code').show();
		$('codelink').setText("Interactive mode");
	} else {
		var content = $('codetext').value;
		setContent(content);
		function load() {
			$('code').hide();
			$('document').show();
			$('codelink').setText("View/edit code");
		}
		load();
	}
}

function getContent() {
	var queries = [];
	$('queries').childElements().each(function(query) {
		var item = {};
		var textarea = query.select('textarea.request')[0];
		item.request = textarea.value;
		item.results = textarea.results;
		queries.push(item);
	});
	var content = Object.toJSON(queries);
	
	return content;
}

function setContent(content) {
	$('queries').deleteChildNodes();
	
	$('welcome').hide();
	
	var queries = content.evalJSON();
	queries.each(function(item) {
		var li = createQuery(null, true, true);
		li.textarea.value = item.request;
		if( item.results != undefined ) {
			setResult(li.ul, item.results);
			li.textarea.results = item.results;
		}
	});
	
	createSortable();
	
	refreshInputSizes();
	
	lastFocus = null;
	if ($('queries').lastChild)
		$('queries').lastChild.textarea.focus();
}

function createLink() {
	var queries = new Array();
	$('queries').childElements().each(function(query) {
		var text = query.select('textarea.request')[0].getText();
		queries[queries.length] = 'queries=' + encodeURIComponent(text);
	});
	var query = queries.join('&');
	location.hash = '#' + btoa(query); //encodeURI(query);
}

function setQueries(queries) {
	var list = [];
	queries.each(function(query) {
		var li = createQuery(null, true, true);
		li.textarea.value = query;
		list.push({'li': li, 'query': query});
	});
	refreshInputSizes();
	function load(index) {
		if (index < list.length) {
			var item = list[index];
			submitQuery(item.li.textarea, function() {
				load(index + 1);
			});
		} else {
			createSortable();
			lastFocus = null;
			if ($('queries').lastChild)
				$('queries').lastChild.textarea.focus();
		}
	}
	load(0);	
}

function loadLink() {
	var hash = location.hash;
	if (hash && hash.length > 1) {
		var params = atob(hash.slice(1)).split('&');
		var queries = [];
		params.each(function(param) {
			if (param.startsWith('queries=')) {
				param = param.slice(8);
				param = decodeURIComponent(param);
				if (param != "")
					queries.push(param);
			}
		});
		setQueries(queries);
		return queries.length > 0;
	} else
		return false;
}

function showGallery() {
	setQueries([
	  '1 + 2 - x * 3 x / y',
	  'Sin[Pi]',
	  'Plot[{Sin[x], Cos[x], Tan[x]}, {x, -3Pi, 3Pi}]',
	  'Plot3D[Exp[x] Cos[y], {x, -2, 1}, {y, -Pi, 2 Pi}]',
	  'translate[graphics_, {dx_,dy_,dz_}] := graphics /. Sphere[{x_,y_,z_}, r_] -> Sphere[{x+dx, y+dy, z+dz}, r]',
	  'sierpinski[block_, size_] := translate[block, #*size*2]& /@ {{0,0,.6124}, {-.2886,-.5,-.204}, {-.2886,.5,-.204}, {.5774,0,-.204}}',
	  'Graphics3D[{Yellow, First[Nest[{sierpinski[First[#], Last[#]], Last[#]*2}&, {Sphere[{0,0,0}, 1], 1}, 3]]}]',
	  'N[E, 30]',
	  'D[Sin[2x] + Log[x] ^ 2, x]',
	  'Integrate[Tan[x] ^ 5, x]',
	  'A = {{1, 2, 3}, {4, 5, 6}, {7, 8, 9}}; MatrixForm[A]',
	  'LinearSolve[A, {1, 1, 1}] // MatrixForm',
	  'Eigenvalues[A]',
	  '# ^ 2 & /@ Range[10]',
	  'Graphics[Table[{EdgeForm[{GrayLevel[0, 0.5]}], Hue[(-11+q+10r)/72, 1, 1, 0.6], Disk[(8-r){Cos[2Pi q/12], Sin [2Pi q/12]}, (8-r)/3]}, {r, 6}, {q, 12}]]'
	]);
}
